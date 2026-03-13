import subprocess

def run_skill(script_path, user_input):

    try:
        result = subprocess.run(
            ["python", script_path, user_input],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return result.stderr

    except Exception as e:
        return str(e)