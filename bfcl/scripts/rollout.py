#!/usr/bin/env python3
"""
BFCL Skill Rollout

Run episodes with skill invocation on BFCL multi-turn benchmark.
Supports:
  - main: greedy rollout with logprobs for entropy computation
  - invoke: branch rollout with skill tools
  - skip_noskill: branch rollout without skill tools
"""

import argparse
import json
import math
import sys
from pathlib import Path

import requests

BASE = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BASE))

from shared.skill_utils import (
    load_skills, build_skill_tool_schema, build_skill_reminder, calc_entropy
)
from shared.vllm_client import vllm_chat

BFCL_DATA_DIR = None  # set via config
SPLIT_MANIFEST = None


def load_config():
    import yaml
    cfg_path = BASE / "configs" / "config.yaml"
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def load_cases(data_dir, category, split, n, ids_file=None):
    manifest_path = Path(data_dir) / "split_manifest.json"
    manifest = json.load(open(manifest_path))
    if ids_file and Path(ids_file).exists():
        id_data = json.load(open(ids_file))
        cases = []
        for cat, id_list in id_data.items():
            id_set = set(id_list)
            data_file = Path(data_dir) / f"BFCL_v4_{cat}.json"
            if not data_file.exists():
                continue
            with open(data_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if obj["id"] in id_set:
                        obj["_category"] = cat
                        cases.append(obj)
        return cases[:n]
    else:
        ids = set(manifest["categories"][category][f"{split}_ids"])
        data_file = Path(data_dir) / f"BFCL_v4_{category}.json"
        cases = []
        with open(data_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj["id"] in ids:
                    cases.append(obj)
                if len(cases) >= n:
                    break
        return cases


_func_doc_cache = {}
FUNC_DOC_MAP = {
    "GorillaFileSystem": "gorilla_file_system.json",
    "MathAPI": "math_api.json",
    "MessageAPI": "message_api.json",
    "TwitterAPI": "posting_api.json",
    "TicketAPI": "ticket_api.json",
    "TradingBot": "trading_bot.json",
    "TravelAPI": "travel_booking.json",
    "VehicleControlAPI": "vehicle_control.json",
    "MemoryAPI_kv": "memory_kv.json",
    "MemoryAPI_vector": "memory_vector.json",
    "MemoryAPI_rec_sum": "memory_rec_sum.json",
}


def load_func_doc(class_name, func_doc_dir):
    if class_name in _func_doc_cache:
        return _func_doc_cache[class_name]
    fname = FUNC_DOC_MAP.get(class_name)
    if fname:
        fpath = Path(func_doc_dir) / fname
        if fpath.exists():
            docs = []
            with open(fpath) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        docs.append(json.loads(line))
            _func_doc_cache[class_name] = docs
            return docs
    return []


def get_bfcl_tools(case, func_doc_dir, extra_funcs=None):
    perm_excluded = set(case.get("excluded_function", []))
    all_missed = set()
    for funcs in case.get("missed_function", {}).values():
        all_missed.update(funcs)
    init_excluded = perm_excluded | all_missed

    tools = []
    for func in case.get("function", []):
        if isinstance(func, dict) and func.get("name") not in init_excluded:
            tools.append({"type": "function", "function": func})
    if tools:
        if extra_funcs:
            for func in extra_funcs:
                if isinstance(func, dict) and func.get("name") not in perm_excluded:
                    tools.append({"type": "function", "function": func})
        return tools

    for class_name in case.get("involved_classes", []):
        for func_doc in load_func_doc(class_name, func_doc_dir):
            if isinstance(func_doc, dict) and func_doc.get("name") not in init_excluded:
                tools.append({"type": "function", "function": func_doc})

    if extra_funcs:
        for func in extra_funcs:
            if isinstance(func, dict) and func.get("name") not in perm_excluded:
                tools.append({"type": "function", "function": func})
    return tools


def inject_skill_body(tool_call_id, skill, skill_name, args):
    body = skill.get("body", "")
    if args:
        body = body.replace("$ARGUMENTS", args)
    return [{
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": f"[Skill: {skill_name}]\n{body}",
    }]


def calc_entropy_seq(logprobs_list, n_tokens=50):
    if not logprobs_list:
        return []
    result = []
    for token_probs in logprobs_list[:n_tokens]:
        lps = list(token_probs.values())
        h = sum(-math.exp(lp) * lp for lp in lps
                if lp is not None and not math.isnan(lp) and not math.isinf(lp))
        result.append(round(h, 6))
    return result


def run_episode(
    url, model, case, all_skills, func_doc_dir,
    mode="main",
    branch_at_turn=0,
    prefix_messages=None,
    temperature=0.0,
    max_tokens=1024,
    top_logprobs=50,
    episode_id=None,
    no_skill=False,
):
    questions = case.get("question", [])
    initial_config = case.get("initial_config", {})
    involved_classes = case.get("involved_classes", [])
    case_id = case.get("id", "unknown")
    exec_model_name = episode_id if episode_id else f"rollout_{mode}"

    missed_function = {int(k): v for k, v in case.get("missed_function", {}).items()}

    if no_skill or mode == "skip_noskill":
        skill_tool = None
        skill_reminder = ""
    else:
        skill_tool = build_skill_tool_schema(all_skills) if all_skills else None
        skill_reminder = build_skill_reminder(all_skills) if all_skills else ""

    if prefix_messages is not None:
        if no_skill or mode == "skip_noskill":
            filtered = []
            i = 0
            while i < len(prefix_messages):
                m = prefix_messages[i]
                if m.get("role") == "user" and "<system-reminder>" in (m.get("content") or ""):
                    i += 1
                    if i < len(prefix_messages) and prefix_messages[i].get("role") == "assistant":
                        i += 1
                    continue
                filtered.append(m)
                i += 1
            messages = filtered
        else:
            messages = list(prefix_messages)
    else:
        bfcl_tools_list = get_bfcl_tools(case, func_doc_dir)
        bfcl_functions = [t["function"] for t in bfcl_tools_list]
        func_doc = json.dumps(bfcl_functions, indent=4) if bfcl_functions else "[]"
        sys_content = (
            "You are an expert in composing functions. "
            "You are given a question and a set of possible functions. "
            "Based on the question, you will need to make one or more function/tool calls to achieve the purpose. "
            "If none of the functions can be used, point it out. "
            "If the given question lacks the parameters required by the function, also point it out.\n\n"
            "You should only return the function calls in your response.\n\n"
            "If you decide to invoke any of the function(s), you MUST put it in the format of "
            "[func_name1(params_name1=params_value1, params_name2=params_value2...), func_name2(params)]. "
            "You SHOULD NOT include any other text in the response.\n\n"
            "At each turn, you should try your best to complete the tasks requested by the user within the current turn. "
            "Continue to output functions to call until you have fulfilled the user's request to the best of your ability. "
            "Once you have no more functions to call, the system will consider the current turn complete and proceed to the next turn or task.\n\n"
            f"Here is a list of functions in JSON format that you can invoke.\n{func_doc}\n"
        )
        if initial_config:
            sys_content += f"\n\nInitial state:\n{json.dumps(initial_config, indent=2)}"
        messages = [{"role": "system", "content": sys_content}]
        if skill_reminder:
            messages.append({"role": "user", "content": skill_reminder})
            messages.append({"role": "assistant", "content": "Understood. I'll use the available skills when appropriate."})

    bfcl_tools = get_bfcl_tools(case, func_doc_dir)
    all_tools = bfcl_tools + ([skill_tool] if skill_tool else [])

    skill_calls = []
    start_turn = branch_at_turn if mode != "main" else 0

    try:
        from bfcl_eval.eval_checker.multi_turn_eval.multi_turn_utils import execute_multi_turn_func_call
        has_exec = True
    except ImportError:
        has_exec = False

    for turn_idx, turn_qs in enumerate(questions):
        if turn_idx < start_turn:
            continue

        if isinstance(turn_qs, list) and len(turn_qs) == 0:
            extra_docs = []
            if turn_idx in missed_function:
                missed_names = missed_function[turn_idx]
                for class_name in involved_classes:
                    for func_doc_entry in load_func_doc(class_name, func_doc_dir):
                        if isinstance(func_doc_entry, dict) and func_doc_entry.get("name") in missed_names:
                            extra_docs.append(func_doc_entry)
                if extra_docs:
                    existing_names = {t["function"]["name"] for t in bfcl_tools}
                    for doc in extra_docs:
                        if doc["name"] not in existing_names:
                            bfcl_tools.append({"type": "function", "function": doc})
                            existing_names.add(doc["name"])
                    all_tools = bfcl_tools + ([skill_tool] if skill_tool else [])
            messages.append({"role": "user", "content": "I have updated some more functions you can choose from. What about now?"})
        elif isinstance(turn_qs, list):
            for q in turn_qs:
                content = q.get("content", str(q)) if isinstance(q, dict) else str(q)
                messages.append({"role": "user", "content": content})
        elif isinstance(turn_qs, dict):
            messages.append({"role": "user", "content": turn_qs.get("content", str(turn_qs))})
        else:
            messages.append({"role": "user", "content": str(turn_qs)})

        for step in range(10):
            lp_count = top_logprobs if mode == "main" else 0
            result = vllm_chat(
                url, model, messages, tools=all_tools,
                temperature=temperature,
                max_tokens=max_tokens,
                top_logprobs=lp_count,
            )

            text = result["text"]
            tool_calls_raw = result["tool_calls"]
            logprobs = result["logprobs"]
            finish_reason = result["finish_reason"]

            if tool_calls_raw:
                messages.append({
                    "role": "assistant",
                    "content": text or None,
                    "tool_calls": tool_calls_raw,
                })

                step_entropy = calc_entropy(logprobs) if (mode == "main" and logprobs) else 0.0

                for tc in tool_calls_raw:
                    tc_id = tc.get("id", f"call_{step}")
                    func = tc.get("function", {})
                    func_name = func.get("name", "")
                    try:
                        raw_args = func.get("arguments", "{}")
                        func_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        if isinstance(func_args, str):
                            try:
                                func_args = json.loads(func_args)
                            except Exception:
                                func_args = {}
                        if not isinstance(func_args, dict):
                            func_args = {}
                    except Exception:
                        func_args = {}

                    if func_name == "Skill":
                        skill_name = func_args.get("skill", "")
                        skill_args_raw = func_args.get("args", "")
                        if isinstance(skill_args_raw, dict):
                            skill_args = json.dumps(skill_args_raw, ensure_ascii=False)
                        else:
                            skill_args = str(skill_args_raw) if skill_args_raw else ""

                        entropy_seq_A = calc_entropy_seq(logprobs, 50) if (mode == "main" and logprobs) else []
                        sc_entry = {
                            "turn_idx": turn_idx,
                            "step": step,
                            "skill_name": skill_name,
                            "skill_args": skill_args,
                            "tool_name": "Skill",
                            "entropy": step_entropy,
                            "entropy_seq_A": entropy_seq_A,
                            "tool_call_id": tc_id,
                            "is_skill": True,
                        }

                        if skill_name in all_skills:
                            injected = inject_skill_body(tc_id, all_skills[skill_name], skill_name, skill_args)
                            messages.extend(injected)

                            if mode == "main":
                                try:
                                    b_result = vllm_chat(
                                        url, model, messages, tools=all_tools,
                                        temperature=0.0, max_tokens=1,
                                        top_logprobs=top_logprobs,
                                    )
                                    sc_entry["entropy_seq_B"] = calc_entropy_seq(b_result["logprobs"], 50) if b_result["logprobs"] else []
                                except Exception:
                                    sc_entry["entropy_seq_B"] = []
                        else:
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": f"Skill '{skill_name}' not found.",
                            })

                        skill_calls.append(sc_entry)

                    else:
                        skill_calls.append({
                            "turn_idx": turn_idx,
                            "step": step,
                            "skill_name": "",
                            "tool_name": func_name,
                            "entropy": step_entropy,
                            "tool_call_id": tc_id,
                            "is_skill": False,
                        })

                        if has_exec:
                            try:
                                args_dict = json.loads(func_args) if isinstance(func_args, str) else (func_args or {})
                                args_str = ", ".join(
                                    f"{k}={repr(v)}" for k, v in args_dict.items()
                                ) if isinstance(args_dict, dict) else ""
                                func_call_str = f"{func_name}({args_str})"
                                exec_results, _ = execute_multi_turn_func_call(
                                    func_call_list=[func_call_str],
                                    initial_config=initial_config,
                                    involved_classes=involved_classes,
                                    model_name=exec_model_name,
                                    test_entry_id=case_id,
                                )
                                tool_content = exec_results[0] if exec_results else "null"
                            except Exception as e:
                                tool_content = f"Error: {e}"
                        else:
                            tool_content = "null"

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": str(tool_content),
                        })
            else:
                messages.append({"role": "assistant", "content": text})
                break

            if finish_reason == "stop":
                break

    return {
        "messages": messages,
        "skill_calls": skill_calls,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vllm-url", default="http://localhost:8000/v1")
    parser.add_argument("--model-name", default="Qwen3-14B")
    parser.add_argument("--category", default="multi_turn_base")
    parser.add_argument("--split", default="train")
    parser.add_argument("--n-cases", type=int, default=200)
    parser.add_argument("--ids-file", default=None)
    parser.add_argument("--skills-dir", required=True)
    parser.add_argument("--data-dir", required=True, help="BFCL data directory")
    parser.add_argument("--func-doc-dir", required=True, help="BFCL multi_turn_func_doc directory")
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-logprobs", type=int, default=50)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    skills = load_skills(args.skills_dir)
    print(f"Loaded {len(skills)} skills from {args.skills_dir}")

    cases = load_cases(args.data_dir, args.category, args.split, args.n_cases, args.ids_file)
    print(f"Total cases: {len(cases)}")

    output_file = Path(args.output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    done_ids = set()
    results = []
    if args.resume and output_file.exists():
        results = json.load(open(output_file))
        done_ids = {r["id"] for r in results}
        print(f"Resuming: {len(done_ids)} done")

    for i, case in enumerate(cases):
        case_id = case["id"]
        if case_id in done_ids:
            continue

        print(f"[{i+1}/{len(cases)}] {case_id}", flush=True)
        try:
            result = run_episode(
                args.vllm_url, args.model_name, case, skills, args.func_doc_dir,
                mode="main",
                temperature=args.temperature,
                top_logprobs=args.top_logprobs,
                episode_id=f"{case_id}_main",
            )
            results.append({
                "id": case_id,
                "category": case.get("_category", args.category),
                "messages": result["messages"],
                "skill_calls": result["skill_calls"],
            })
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        if len(results) % 10 == 0:
            with open(output_file, "w") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

    with open(output_file, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(results)} results to {output_file}")


if __name__ == "__main__":
    main()
