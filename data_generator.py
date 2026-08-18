from dotenv import load_dotenv
import pandas as pd
import ollama
import time
import re
import os
from datasets import load_dataset
from sandbox import run_in_sandbox

load_dotenv()

def extract_code(text):
    matches = re.findall(r'```(?:.*?)\n(.*?)```', text, re.DOTALL)
    if matches:
        code = matches[-1].strip()
    else:
        code = text.strip()
        
    code = re.sub(r'int\s+main\s*\(.*?\)\s*\{.*', '', code, flags=re.DOTALL)
    code = re.sub(r'public\s+static\s+void\s+main\s*\(.*?\)\s*\{.*', '', code, flags=re.DOTALL)
    return code.strip()

def extract_bug_type(text):
    match = re.search(r'BUG_TYPE:\s*(.*)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip().lower()
    return "unknown"

def merge_code(prompt, clean_code):
    prompt_lines = [line for line in prompt.split('\n') if line.strip() != '']
    if not prompt_lines: return clean_code
    signature_line = prompt_lines[-1]
    
    func_name = ""
    if '(' in signature_line:
        before_paren = signature_line.split('(')[0]
        before_paren = re.sub(r'[^a-zA-Z0-9_]', ' ', before_paren)
        words = before_paren.strip().split()
        if words: func_name = words[-1]
            
    if "class Solution" in clean_code and "class Solution" in prompt:
        imports = [line for line in prompt.split('\n') if line.startswith('import ') or line.startswith('#include')]
        merged = '\n'.join(imports) + '\n\n' + clean_code
    elif func_name and func_name in clean_code:
        imports_only = prompt[:prompt.rfind(signature_line)]
        merged = imports_only + "\n" + clean_code
    else:
        merged = prompt + "\n" + clean_code
        
    open_braces = merged.count('{')
    close_braces = merged.count('}')
    if open_braces > close_braces:
        merged += "\n" + "}" * (open_braces - close_braces)
        
    return merged

def query_llm(prompt, model_name):
    try:
        response = ollama.chat(model=model_name, messages=[
            {"role": "user", "content": prompt}
        ])
        return response['message']['content']
    except Exception as e:
        print(f"  [!] Error with model {model_name}: {e}")
        return "Error"

def build_llm_prompt(language, prompt_sig, buggy_solution):
    return f"""You are an expert {language} developer.

I have a buggy code snippet. You need to diagnose the bug and provide the fixed code.

--- PROMPT & SIGNATURE ---
{prompt_sig}

--- BUGGY SOLUTION ---
{buggy_solution}

Task:
1. Classify the bug into EXACTLY ONE of these 6 categories:
   - value misuse
   - missing logic
   - excess logic
   - operator misuse
   - variable misuse
   - function misuse

2. Provide the fully fixed code inside a markdown code block.

You must strictly output your classification exactly like this:
BUG_TYPE: <category>

Then provide the code block.
"""

def run_pipeline():  
    languages_to_test = ["python", "cpp", "java", "js"]
    models_to_test = ["qwen2.5-coder:7b", "deepseek-coder:6.7b", "llama3.1:8b"]
    
    csv_filename = "dataset_v1.csv"
    results = []
    completed_tests = set()
    
    if os.path.exists(csv_filename):
        df_existing = pd.read_csv(csv_filename)
        results = df_existing.to_dict('records')
        for row in results:
            completed_tests.add((row['model_name'], row['language'], row['task_id']))
        print(f"Loaded {len(completed_tests)} previously completed tests.\n")
        
    for model_name in models_to_test:
        print(f"\n========================================")
        print(f" TESTING MODEL: {model_name}")
        print(f"========================================")
        
        for lang in languages_to_test:
            print(f"\nLoading HumanEvalPack for {lang}...")
            sandbox_lang = "javascript" if lang == "js" else lang
            
            try:
                dataset = load_dataset("bigcode/humanevalpack", lang)
            except Exception:
                continue
            
            for row in list(dataset["test"]):
                task_id = row["task_id"]
                prompt_sig = row["prompt"]
                buggy_solution = row["buggy_solution"]
                test_harness = row["test"]
                true_bug_type = row["bug_type"]
                true_failure_symptom = row["failure_symptoms"]
                
                if (model_name, lang, task_id) in completed_tests:
                    continue
                    
                print(f"Testing {task_id} ...", end=" ", flush=True)
                
                llm_prompt = build_llm_prompt(lang, prompt_sig, buggy_solution)
                generated_text = query_llm(llm_prompt, model_name)
                
                if generated_text == "Error": 
                    print("❌ LLM Error")
                    continue
                    
                predicted_bug_type = extract_bug_type(generated_text)
                clean_code = extract_code(generated_text)
                merged_code = merge_code(prompt_sig, clean_code)
                full_code = merged_code + "\n\n" + test_harness
                
                test_result = run_in_sandbox(full_code, sandbox_lang)
                fix_success = 1 if test_result['status'] == "success" else 0
                diagnosis_match = 1 if true_bug_type.lower() in predicted_bug_type else 0
                
                if fix_success:
                    print(f"✅ Fixed! (Guessed: {predicted_bug_type})")
                else:
                    print(f"❌ Failed! (Guessed: {predicted_bug_type})")
                    
                results.append({
                    "task_id": task_id,
                    "language": lang,
                    "model_name": model_name,
                    "true_bug_type": true_bug_type,
                    "true_failure_symptom": true_failure_symptom,
                    "predicted_bug_type": predicted_bug_type,
                    "diagnosis_match": diagnosis_match,
                    "code_length": len(clean_code.split('\n')),
                    "fix_success": fix_success
                })
                pd.DataFrame(results).to_csv(csv_filename, index=False)
                completed_tests.add((model_name, lang, task_id))

    print(f"\n[SUCCESS] Finished! Saved to {csv_filename}!")

if __name__ == "__main__":
    run_pipeline()
