from flujoflujoclass import (
    InputReader,
    CostModel,
    CashFlowModel,
    ReportGenerator
)

# =========================
# 1. INPUTS
# =========================
reader = InputReader("data_entrada.xlsx") #aqui es el df que trabajamos en el treeview, las 3 pestañas. Luego lo vemos a detalle
data = reader.leer()

# =========================
# 2. COSTOS
# =========================
cost_model = CostModel(data)
costos = cost_model.calcular()

# =========================
# 3. SCHEDULE INPUT (USER)
# =========================
schedule_input = {
    "FC": "0.3,0.7", #
    "VCOP": "0.5,1"
}

# =========================
# 3.1 PARSE SCHEDULE
# =========================
schedule = {
    "FC": [float(x) for x in schedule_input["FC"].split(",")],
    "VCOP": [float(x) for x in schedule_input["VCOP"].split(",")]
}

# =========================
# 4. PARAMS (DEBE IR ANTES DE USARLOS)
# =========================
params = {
    "vida": 18, #tiempo de vida del proyecto
    "tasa_impuesto": 0.35, #intereses para impuestos. Pago con desfase de 1 año
    "metodo_dep": 0, # 0:lineal, 1 MACRS
    "periodo_dep": 10, #usado para dprciacion lineal
    "tipo_macrs": 0, # 0:MACRS5, 1:MACRS7, 2:MACRS15
    "schedule": schedule,
    "tasa_interes": 0.15 #tasa de retorno de inversión
}

# =========================
# 5. REPORT GENERATOR
# =========================
reporte = ReportGenerator()

# =========================
# 6. BUILD SCHEDULE (SI LO USAS)
# =========================
schedule_full = reporte.construir_schedule(schedule, params["vida"])

params["schedule"] = schedule_full
# =========================
# 7. CASH FLOW
# =========================
cf_model = CashFlowModel(costos, params)
cf = cf_model.calcular()

# =========================
# 8. OUTPUT
# =========================
#reporte.exportar_costos_detallado("reporte_costoszz.xlsx", data, costos)
reporte.exportar_cashflow("Economic Analysis31.xlsx", cf, params, costos, data)

print("Modelo ejecutado correctamente 🚀")