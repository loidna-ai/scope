import json
import re

file_path = "notebook/Agent_4_Necking_Expert.ipynb"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

def text_replacer(text):
    if not isinstance(text, str):
        return text
    
    # Imports and Modules
    text = text.replace("src.prompts.partial_break_expert_prompts", "src.prompts.necking_expert_prompts")
    text = text.replace("src.graphs.partial_break_expert_graph", "src.graphs.necking_expert_graph")
    text = text.replace("partial_break_expert_wrapper_node", "necking_expert_wrapper_node")
    text = text.replace("src.nodes.partial_break_nodes", "src.nodes.necking_nodes")
    
    # Labels and Titles
    text = text.replace("Partial Break Expert", "Necking Expert")
    text = text.replace("PartialBreak", "Necking")
    text = text.replace("반단선 전문가", "반단선(Necking) 전문가")
    
    # Result Keys
    text = text.replace('.get("partial_break", {})', '.get("necking", {})')
    text = text.replace('"partial_break": {', '"necking": {')
    
    # Variable names in state/results
    text = text.replace("partial_break_step1_result", "necking_step1_result")
    text = text.replace("partial_break_step2_result", "necking_step2_result")
    text = text.replace("partial_break_step3_result", "necking_step3_result")
    
    return text

def recursive_replace(obj):
    if isinstance(obj, dict):
        return {k: recursive_replace(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [recursive_replace(item) for item in obj]
    elif isinstance(obj, str):
        return text_replacer(obj)
    else:
        return obj

new_data = recursive_replace(data)

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(new_data, f, indent=1, ensure_ascii=False)

print("Notebook updated successfully.")
