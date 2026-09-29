import os
import platform
import shutil

try:
    import psutil
except ImportError:
    psutil = None


class Module:
    def __init__(self, context=None):
        self.context = context or {}

    def tools(self):
        return [
            {
                "name": "status",
                "description": "Read current CPU, RAM, disk and operating-system status from this computer.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]

    def run(self, action, arguments):
        if action != "status":
            raise KeyError(action)

        root = os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"
        disk = shutil.disk_usage(root)

        result = {
            "os": platform.platform(),
            "processor": platform.processor(),
            "disk_total_gb": round(disk.total / (1024**3), 2),
            "disk_used_gb": round(disk.used / (1024**3), 2),
            "disk_free_gb": round(disk.free / (1024**3), 2),
        }

        if psutil:
            result.update({
                "cpu_percent": psutil.cpu_percent(interval=0.15),
                "ram_percent": psutil.virtual_memory().percent,
                "ram_used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
                "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            })
        return result
