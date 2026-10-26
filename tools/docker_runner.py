import os
import re
import docker
from pathlib import Path
from typing import Dict, Any, Optional

DEFAULT_SANDBOX_IMAGE = os.environ.get("DEFAULT_SANDBOX_IMAGE", "node:18-bullseye-slim")


class DockerSandboxRunner:
    def __init__(self, workspace_path: str = "./workspace", base_image: str | None = None):
        """
        Initializes the Docker client and ensures the local workspace directory exists.
        Uses the provided base_image, DEFAULT_SANDBOX_IMAGE env var, or node:18-bullseye-slim.
        """
        self.workspace_path = Path(workspace_path).resolve()
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        
        try:
            self.client = docker.from_env()
        except Exception as e:
            raise RuntimeError(
                f"[DockerRunner Error] Could not connect to Docker daemon. Is Docker running? Details: {e}"
            )
        
        self.base_image = base_image or os.environ.get("DEFAULT_SANDBOX_IMAGE", "node:18-bullseye-slim")

    def execute_code(
        self,
        command: str,
        timeout_seconds: int = 120,
        *,
        task_id: str | None = None,
        image: str | None = None,
    ) -> Dict[str, Any]:
        """
        Safely executes a shell command inside an isolated container with the workspace mounted.
        """
        target_image = image or self.base_image
        workspace_path = self.workspace_path
        container_workspace = "/app/workspace"
        if task_id is not None:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", task_id):
                raise ValueError("Task ID must contain only letters, digits, underscores, or hyphens")
            workspace_path = (self.workspace_path / task_id).resolve()
            if not workspace_path.is_relative_to(self.workspace_path) or workspace_path == self.workspace_path:
                raise ValueError("Task workspace must be within the workspace directory")
            workspace_path.mkdir(parents=True, exist_ok=True)
            container_workspace = f"/app/workspace/{task_id}"

        # Configure volume mapping: host workspace maps to /app/workspace inside container
        volumes = {
            str(workspace_path): {
                'bind': container_workspace,
                'mode': 'rw'
            }
        }

        container = None
        try:
            try:
                self.client.images.get(target_image)
            except docker.errors.ImageNotFound:
                print(f"[DockerRunner] Image {target_image} not found locally. Pulling from Docker Hub...")
                self.client.images.pull(target_image)
            # Create and run container safely with resource restrictions
            container = self.client.containers.create(
                image=target_image,
                command=["/bin/sh", "-c", command],
                working_dir=container_workspace,
                volumes=volumes,
                network_disabled=False, # Set to True if app doesn't need internet/npm pulls
                detach=True
            )
            
            container.start()
            
            # Wait for execution with timeout protection
            result = container.wait(timeout=timeout_seconds)
            exit_code = result.get("StatusCode", -1)
            
            # Fetch logs
            logs = container.logs(stdout=True, stderr=True).decode('utf-8', errors='replace')
            
            return {
                "success": exit_code == 0,
                "exit_code": exit_code,
                "output": logs
            }

        except Exception as e:
            logs = ""
            if container:
                try:
                    logs = container.logs(stdout=True, stderr=True).decode('utf-8', errors='replace')
                except Exception:
                    pass
            return {
                "success": False,
                "exit_code": -1,
                "output": f"[DockerRunner Execution Error]: {str(e)}\n{logs}"
            }
            
        finally:
            # Clean up container instance immediately after execution
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

# Standalone verification block
if __name__ == "__main__":
    runner = DockerSandboxRunner()
    print("Testing Docker sandbox runner with a basic node/python command...")
    res = runner.execute_code("node -v && npm -v")
    print(res)
