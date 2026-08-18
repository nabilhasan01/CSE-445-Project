import docker
import os
import tempfile

# Docker Desktop (Windows) Connector
client = docker.from_env()
IMAGE_NAME = "llm-eval-sandbox"

def build_sandbox_image():
    print(f"Creating Docker image '{IMAGE_NAME}'")
    client.images.build(path=".", tag=IMAGE_NAME)
    print("[SUCCESS] Sandbox image Created")

# Write the code in a temp file and run it inside docker
# Returns the execution output and errors
def run_in_sandbox(code, language):
    extensions = {
        "python": ".py", "javascript": ".js", "cpp": ".cpp", 
        "java": ".java", "go": ".go", "rust": ".rs"
    }
    
    ext = extensions.get(language.lower(), ".txt")
    
    temp_dir = os.path.abspath("temp_code")
    os.makedirs(temp_dir, exist_ok=True)
    
    filename = "Main.java" if language.lower() == "java" else f"script{ext}"
    filepath = os.path.join(temp_dir, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(code)
        
    if language.lower() == "python":
        cmd = f"timeout 10 python3 /sandbox/{filename}"
    elif language.lower() == "javascript":
        cmd = f"timeout 10 node /sandbox/{filename}"
    elif language.lower() == "cpp":
        cmd = f"sh -c 'g++ /sandbox/{filename} -o /sandbox/out && timeout 10 /sandbox/out'"
    elif language.lower() == "java":
        cmd = f"sh -c 'cd /sandbox && javac {filename} && timeout 10 java -ea Main'"
    elif language.lower() == "go":
        cmd = f"timeout 10 go run /sandbox/{filename}"
    elif language.lower() == "rust":
        cmd = f"sh -c 'rustc /sandbox/{filename} -o /sandbox/out && timeout 10 /sandbox/out'"
    else:
        return {"status": "failed", "error": "Unsupported language"}

    try:
        client.containers.run(
            IMAGE_NAME,
            command=cmd,
            volumes={temp_dir: {'bind': '/sandbox', 'mode': 'rw'}},
            remove=True,
            network_disabled=True,
            mem_limit="1g",
            cpu_quota=200000
        )
        return {"status": "success", "error": None}
        
    except docker.errors.ContainerError as e:
        if e.exit_status == 124:
            return {"status": "failed", "error": "TimeoutError: Infinite loop detected (Execution took >10s)"}
        error_msg = ""
        if e.stderr:
            error_msg = e.stderr.decode('utf-8', errors='replace')
        if not error_msg.strip() and hasattr(e, 'output') and e.output:
            error_msg = e.output.decode('utf-8', errors='replace')
        if not error_msg.strip():
            error_msg = str(e)
        return {"status": "failed", "error": error_msg}
    except Exception as e:
        return {"status": "failed", "error": str(e)}
