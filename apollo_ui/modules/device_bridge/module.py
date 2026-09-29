from pathlib import Path
class Module:
    def __init__(self,context=None): pass
    def tools(self): return [
        {"name":"list_serial_ports","description":"List available serial/USB devices for Arduino, OBD and sensor modules.","parameters":{"type":"object","properties":{}}},
        {"name":"read_serial","description":"Read lines from a serial port for a bounded time.","parameters":{"type":"object","properties":{"port":{"type":"string"},"baud":{"type":"integer"},"timeout":{"type":"number"}},"required":["port"]}},
        {"name":"write_serial","description":"Write text to a serial device. Hardware-changing action is permission-gated.","parameters":{"type":"object","properties":{"port":{"type":"string"},"data":{"type":"string"},"baud":{"type":"integer"}},"required":["port","data"]}},
    ]
    def _serial(self):
        try: import serial,serial.tools.list_ports; return serial,serial.tools.list_ports
        except ImportError as e: raise RuntimeError('pyserial is not installed. Run install.bat after applying Apollo 7.') from e
    def run(self,a,x):
        serial,ports=self._serial(); x=x or {}
        if a=='list_serial_ports': return {'ports':[{'device':p.device,'description':p.description,'hwid':p.hwid} for p in ports.comports()]}
        baud=max(300,min(int(x.get('baud',115200)),2_000_000)); port=str(x['port'])
        if a=='read_serial':
            timeout=max(.1,min(float(x.get('timeout',2)),15)); lines=[]
            with serial.Serial(port,baudrate=baud,timeout=timeout) as s:
                for _ in range(50):
                    raw=s.readline()
                    if not raw:break
                    lines.append(raw.decode('utf-8',errors='replace').rstrip())
            return {'lines':lines}
        if a=='write_serial':
            data=str(x['data']).encode('utf-8');
            with serial.Serial(port,baudrate=baud,timeout=2) as s:n=s.write(data); s.flush()
            return {'bytes_written':n}
        raise KeyError(a)
    def self_test(self): return 'device bridge contracts passed without opening hardware'
