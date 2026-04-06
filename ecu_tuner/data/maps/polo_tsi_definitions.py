"""
data/maps/polo_tsi_definitions.py
==================================
Definiciones específicas para VW Polo 1.0 TSI / 1.4 TSI.
ECU: Bosch ME17.5.22

PARA USO DIDÁCTICO - OFFSETS SIMULADOS
"""

VW_POLO_1_0_TSI = {
    "engine": "1.0 TSI",
    "displacement_cc": 999,
    "power_ps": 95,
    "torque_nm": 175,
    "compression": 10.5,
    "fuel": "Gasolina 95/98",
    "injector_size_cc": 440,
    "turbo": "IHI VF40 / BorgWarner",
    "boost_stock_mbar": 1200,
}

VW_POLO_1_4_TSI = {
    "engine": "1.4 TSI",
    "displacement_cc": 1395,
    "power_ps": 150,
    "torque_nm": 250,
    "compression": 10.0,
    "fuel": "Gasolina 95/98",
    "injector_size_cc": 550,
    "turbo": "BorgWarner K03",
    "boost_stock_mbar": 1500,
}

MAP_CONFIGS = {
    "injection_time": {
        "ecu_offset": 0x14A00,
        "scale": 0.0039,
        "unit": "ms",
        "typical_range": [1.5, 8.0],
    },
    "boost_pressure": {
        "ecu_offset": 0x1C800,
        "scale": 0.1,
        "unit": "mbar",
        "typical_range": [800, 2200],
    },
    "ignition_advance": {
        "ecu_offset": 0x16E00,
        "scale": 0.1,
        "unit": "° BTDC",
        "typical_range": [5.0, 40.0],
    },
    "torque_limiter": {
        "ecu_offset": 0x24800,
        "scale": 0.25,
        "unit": "Nm",
        "typical_range": [100, 400],
    },
    "lamda_correction": {
        "ecu_offset": 0x1A400,
        "scale": 0.001,
        "unit": "lambda",
        "typical_range": [0.95, 1.05],
    },
}
