import os
import json 
import subprocess 
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

class GraphifyVaultManager:
    def __init__(
        self,
        vault_path: str = "./vault",
        output_dir: Optional[str] = None,
        ensure_dirs: bool = True,
    ):
        self.vault_path = Path(vault_path).resolve()
        # Graphify typically outputs graph artifacts into a target directory (defaults to vault/.graphify)
        self.output_dir = Path(output_dir).resolve() if output_dir else self.vault_path / ".graphify"
        self.graph_json_path = self.output_dir / "graph.json"

        if ensure_dirs:
            self.vault_path.mkdir(parents=True, exist_ok=True)
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def build_graph(self, incremental: bool = True) -> bool:
        """
        Triggers the graphify CLI to parse the Obsidian vault and build/update the knowledge graph.
        """
        if not self.vault_path.exists():
            raise FileNotFoundError(f"Vault path does not exist: {self.vault_path}")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [sys.executable, "-m", "graphify", "extract", str(self.vault_path)]
        if not incremental:
            cmd.append("--force")
        environment = {**os.environ, "GRAPHIFY_OUT": str(self.output_dir)}

        try:
            # Run graphify process safely
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                env=environment,
                timeout=300,
            )
            if not self.graph_json_path.is_file():
                if os.environ.get("BUILDRELAY_DEBUG"):
                    print(f"[GraphifyTool Error] Graph output missing: {self.graph_json_path}")
                return False
            return True
        except subprocess.TimeoutExpired:
            if os.environ.get("BUILDRELAY_DEBUG"):
                print("[GraphifyTool Error] Graph build timed out after 300 seconds")
            return False
        except subprocess.CalledProcessError as e:
            if os.environ.get("BUILDRELAY_DEBUG"):
                print(f"[GraphifyTool Error] Subprocess failed with code {e.returncode}")
                print(f"Stdout: {e.stdout}")
                print(f"Stderr: {e.stderr}")
            else:
                debug_log = self.output_dir.parent / ".state" / "graphify_debug.log"
                try:
                    debug_log.parent.mkdir(parents=True, exist_ok=True)
                    debug_log.write_text(
                        f"Return code: {e.returncode}\n--- stdout ---\n{e.stdout}\n--- stderr ---\n{e.stderr}",
                        encoding="utf-8",
                    )
                except Exception:
                    pass
            return False
        except FileNotFoundError:
            if os.environ.get("BUILDRELAY_DEBUG"):
                print("[GraphifyTool Error] 'graphify' CLI command not found. Ensure 'graphifyy' is installed in your .venv.")
            return False

    def load_graph(self) -> Dict[str, Any]:
        """
        Loads the generated graph.json structure into memory for traversal.
        """
        if not self.graph_json_path.exists():
            print(f"[GraphifyTool Warning] graph.json not found at {self.graph_json_path}. Building graph first...")
            success = self.build_graph(incremental=False)
            if not success or not self.graph_json_path.exists():
                return {"nodes": [], "edges": []}

        try:
            with open(self.graph_json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"[GraphifyTool Error] Failed to parse graph.json: {e}")
            return {"nodes": [], "edges": []}

    def query_nodes(self, search_term: str) -> List[Dict[str, Any]]:
        """
        Searches nodes in the graph matching a keyword (useful for finding tasks or specs).
        """
        data = self.load_graph()
        nodes = data.get("nodes", [])
        term = search_term.lower()
        
        matches = [
            node for node in nodes 
            if any(term in str(node.get(key, "")).lower()
                   for key in ("id", "label", "source_file", "properties"))
        ]
        return matches

    def get_neighbors(self, node_id: str) -> List[Dict[str, Any]]:
        """
        Finds direct downstream/upstream connected nodes (useful for checking related research or specs).
        """
        data = self.load_graph()
        edges = data.get("edges", [])
        nodes = {n.get("id"): n for n in data.get("nodes", [])}
        
        neighbor_ids = set()
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            if source == node_id:
                neighbor_ids.add(target)
            elif target == node_id:
                neighbor_ids.add(source)
                
        return [nodes[nid] for nid in neighbor_ids if nid in nodes]

    def resolve_note_sources(self, nodes: List[Dict[str, Any]]) -> list[str]:
        """Resolve Graphify source files to existing Markdown paths within this vault."""
        sources = set()
        for node in nodes:
            properties = node.get("properties")
            properties = properties if isinstance(properties, dict) else {}
            source = node.get("source_file") or properties.get("source_file")
            if not isinstance(source, str) or not source.strip():
                continue
            try:
                path = Path(source)
                path = (self.vault_path / path).resolve() if not path.is_absolute() else path.resolve()
                if path.is_relative_to(self.vault_path) and path.suffix.lower() == ".md" and path.is_file():
                    sources.add(path.relative_to(self.vault_path).as_posix())
            except (OSError, ValueError, RuntimeError):
                # Stale or malformed graph paths must not prevent saving a report.
                continue
        return sorted(sources)

# Reference to unbound method for explicit testing when mocked in fixtures
_original_build_graph = GraphifyVaultManager.build_graph

# Quick standalone test execution block
if __name__ == "__main__":
    manager = GraphifyVaultManager()
    print("Testing GraphifyVaultManager initialization...")
    manager.build_graph(incremental=False)
