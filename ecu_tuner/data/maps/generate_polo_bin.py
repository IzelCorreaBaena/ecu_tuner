"""
data/maps/generate_polo_bin.py
Genera un archivo .bin de ejemplo para VW Polo 1.0 TSI
"""
import struct
import random

FLASH_SIZE_KB = 2048
FLASH_SIZE = FLASH_SIZE_KB * 1024

data = bytearray(FLASH_SIZE)

for i in range(FLASH_SIZE):
    if i < 256:
        data[i] = random.randint(0, 255)
    elif (i + 0x100) % 0x400 < 0x380:
        data[i] = random.randint(0, 254)
    else:
        data[i] = 0xFF

INJECTION_OFFSET = 0x14A00
for row in range(16):
    for col in range(16):
        rpm = 700 + col * 400
        load = 10 + row * 10
        injection = 2.5 + (rpm / 3000) * (load / 50)
        raw_val = int(injection / 0.0039)
        offset = INJECTION_OFFSET + (row * 16 + col) * 2
        data[offset:offset+2] = struct.pack('<H', raw_val)

BOOST_OFFSET = 0x1C800
for row in range(12):
    for col in range(16):
        boost = 800 + row * 120 + (col * 50)
        raw_val = int(boost / 0.1)
        offset = BOOST_OFFSET + (row * 16 + col) * 2
        data[offset:offset+2] = struct.pack('<H', raw_val)

IGNITION_OFFSET = 0x16E00
for row in range(16):
    for col in range(16):
        rpm = 700 + col * 400
        if rpm < 3000:
            advance = 30.0
        else:
            advance = 30.0 - (rpm - 3000) * 0.005
        raw_val = int(advance / 0.1)
        if raw_val < 0:
            raw_val = raw_val & 0xFFFF
        offset = IGNITION_OFFSET + (row * 16 + col) * 2
        data[offset:offset+2] = struct.pack('<H', raw_val)

CHECKSUM_OFFSET = 0x0BFF8
import zlib
data_copy = bytearray(data)
data_copy[CHECKSUM_OFFSET:CHECKSUM_OFFSET+4] = b'\x00\x00\x00\x00'
checksum = zlib.crc32(data_copy) & 0xFFFFFFFF
data[CHECKSUM_OFFSET:CHECKSUM_OFFSET+4] = struct.pack('<I', checksum)

header = b'VWPO' + b'\x00' * 12
header += struct.pack('<I', 0x14A00)
data[0:16] = header

with open('vw_polo_1.0_tsi_stock.bin', 'wb') as f:
    f.write(data)

print(f"Archivo generado: vw_polo_1.0_tsi_stock.bin ({FLASH_SIZE_KB} KB)")
print(f"Checksum: 0x{checksum:08X}")
