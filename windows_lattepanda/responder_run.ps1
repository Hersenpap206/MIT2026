$env:LOODS_DEVICE   = "LP2"
$env:LOODS_HARDWARE = "LattePanda"
Set-Location "D:\Loods WP3\MIT2026"
& "C:\Users\LattePanda\AppData\Local\Programs\Python\Python312\python.exe" dialogue\mqtt_bridge.py --rol responder --broker 192.168.1.115 *> C:\Windows\Temp\responder.out
