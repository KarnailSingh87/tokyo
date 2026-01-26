import subprocess
import sys
import platform
from pathlib import Path

print("Installing requirements...")
subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)

print("Installing Playwright browsers...")
subprocess.run([sys.executable, "-m", "playwright", "install"], check=True)

if platform.system() == "Windows":
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        postinstall = Path(sys.executable).parent / "Scripts" / "pywin32_postinstall.py"
        print(
            "\n⚠️  pywin32 did not install correctly — desktop shortcut creation "
            "will fall back to a slower method that may not work on this machine.\n"
            "    Try fixing it manually with:\n"
            f'    "{sys.executable}" -m pip install --force-reinstall pywin32\n'
            f'    "{sys.executable}" "{postinstall}" -install\n'
        )

# Ensure TOKYO-X config directories exist
config_dir = Path(__file__).parent / "config"
logs_dir = Path(__file__).parent / "logs"
workspace_dir = Path(__file__).parent / "workspace"
for d in (config_dir, logs_dir, workspace_dir):
    d.mkdir(exist_ok=True)

# Create default configs if missing
managers_json = config_dir / "managers.json"
if not managers_json.exists():
    managers_json.write_text("""{
  "version": "0.1.0",
  "ceo": { "name": "Kapil", "role": "CEO" },
  "orchestrator": { "id": "tokyo-x", "role": "Orchestrator", "modelDefault": "openai:gpt-4o-mini" },
  "managers": [
    { "id": "mgr.research", "name": "Research Manager", "domain": "research", "defaultModel": "openrouter:perplexity/sonar-pro", "maxRiskTier": 1,
      "workers": [{"id": "w.web", "name": "Web Researcher", "tools": ["browser.search", "browser.open"], "maxRiskTier": 1}] },
    { "id": "mgr.code", "name": "Code Manager", "domain": "engineering", "defaultModel": "openai:gpt-4o", "maxRiskTier": 2,
      "workers": [{"id": "w.coder", "name": "Coder", "tools": ["fs.read", "fs.write"], "maxRiskTier": 1}] },
    { "id": "mgr.pcops", "name": "PC Ops Manager", "domain": "local-machine", "defaultModel": "openai:gpt-4o-mini", "maxRiskTier": 2,
      "workers": [{"id": "w.files", "name": "File Worker", "tools": ["fs.read", "fs.write", "fs.delete"], "maxRiskTier": 1}] },
    { "id": "mgr.memory", "name": "Memory Manager", "domain": "memory", "defaultModel": "openai:gpt-4o-mini", "maxRiskTier": 0,
      "workers": [{"id": "w.twin", "name": "Memory Curator", "tools": ["memory.get", "memory.set"], "maxRiskTier": 0}] }
  ]
}""")

perms_json = config_dir / "permissions.json"
if not perms_json.exists():
    perms_json.write_text("""{
  "version": "0.1.0",
  "defaultVerdict": "CONFIRM",
  "rules": [
    { "id": "deny-destructive", "priority": 100, "verdict": "DENY", "reason": "destructive commands",
      "categories": ["terminal"], "argRegex": { "arg": "command", "pattern": "(rm\\s+-rf\\s+/|mkfs|dd\\s+if=.*of=/dev/|shutdown|reboot)" } },
    { "id": "allow-read", "priority": 60, "verdict": "ALLOW", "reason": "read-only", "tools": ["fs.read", "fs.search"] },
    { "id": "confirm-write", "priority": 50, "verdict": "CONFIRM", "reason": "file write", "tools": ["fs.write", "fs.delete"] },
    { "id": "confirm-terminal", "priority": 40, "verdict": "CONFIRM", "reason": "shell exec", "categories": ["terminal"] },
    { "id": "allow-voice", "priority": 30, "verdict": "ALLOW", "reason": "voice IO", "tools": ["voice.stt", "voice.tts"] },
    { "id": "allow-memory", "priority": 30, "verdict": "ALLOW", "reason": "memory ops", "tools": ["memory.get", "memory.set"] }
  ]
}""")

voices_json = config_dir / "voices.json"
if not voices_json.exists():
    voices_json.write_text("""{
  "version": "0.1.0", "defaultPreset": "nova", "voiceIdEnv": "ELEVENLABS_VOICE_ID",
  "presets": [
    { "id": "nova", "name": "Nova", "description": "bright", "stability": 0.5, "similarityBoost": 0.75, "style": 0.15 },
    { "id": "atlas", "name": "Atlas", "description": "deep", "stability": 0.65, "similarityBoost": 0.8, "style": 0.1 },
    { "id": "sage", "name": "Sage", "description": "warm", "stability": 0.55, "similarityBoost": 0.7, "style": 0.25 }
  ]
}""")

models_json = config_dir / "models.json"
if not models_json.exists():
    models_json.write_text("""{
  "version": "0.1.0",
  "usdPerMTokens": { "input": { "gpt-4o-mini": 0.15, "gpt-4o": 2.5 }, "output": { "gpt-4o-mini": 0.6, "gpt-4o": 10.0 } },
  "unknownModelFallback": { "input": 1.0, "output": 2.0 }
}""")

skills_json = config_dir / "skills.json"
if not skills_json.exists():
    skills_json.write_text("""{
  "version": "0.1.0",
  "skills": [
    { "id": "repo-doctor", "name": "Repo Doctor", "description": "Health check", "promptTemplate": "Analyze repo at {{workspace}}. Context: {{context}}", "allowedTools": ["terminal.exec", "fs.read"], "modelSpec": ["openai:gpt-4o"] }
  ]
}""")

print("\n✅ Setup complete! Run 'python main.py' to start MARK LI.")

