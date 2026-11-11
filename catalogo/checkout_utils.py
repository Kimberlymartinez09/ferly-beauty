# catalogo/checkout_utils.py
"""Funciones auxiliares para el proceso de checkout — W14.

Separadas de views.py para facilitar las pruebas unitarias.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from clientes.models import Cliente
from configuracion.models import ConfiguracionERP
from ventas.models import Pedido


def calcular_totales(carrito: dict) -> dict:
    """Calcula subtotal, IVA y total del carrito.

    Args:
        carrito: dict de sesión con estructura
                 {str(pk): {precio: str, cantidad: int, ...}}

    Returns:
        dict con subtotal, iva_pct, iva_monto, total (todos Decimal).
    """
    config = ConfiguracionERP.get_instance()
    iva_pct_valor = Decimal(str(config.iva_porcentaje))
    iva_pct = iva_pct_valor / Decimal('100')

    subtotal = sum(
        (Decimal(datos['precio']) * int(datos['cantidad'])
         for datos in carrito.values()),
        Decimal('0.00'),
    )
    iva_monto = (subtotal * iva_pct).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    total = subtotal + iva_monto

    return {
        'subtotal': subtotal,
        'iva_pct': iva_pct_valor,
        'iva_monto': iva_monto,
        'total': total,
    }


def armar_items(carrito: dict) -> list:
    """Convierte el carrito de sesión en una lista con el subtotal por línea.

    Returns:
        list de dicts con nombre, precio, cantidad y subtotal (Decimal).
    """
    items = []
    for datos in carrito.values():
        precio = Decimal(datos['precio'])
        cantidad = int(datos['cantidad'])
        items.append({
            'nombre': datos['nombre'],
            'precio': precio,
            'cantidad': cantidad,
            'subtotal': precio * cantidad,
        })
    return items


def obtener_o_crear_cliente(user) -> Cliente:
    """Obtiene o crea un Cliente del ERP vinculado al usuario Django.

    Usa el correo del usuario si existe; si no, genera uno temporal.
    """
    correo = user.email or f'{user.username}@erp.local'
    nombre_completo = user.get_full_name()
    nombre = nombre_completo or user.username

    cliente, creado = Cliente.objects.get_or_create(
        correo=correo,
        defaults={'nombre': nombre, 'activo': True},
    )

    if not creado and nombre_completo and cliente.nombre != nombre_completo:
        cliente.nombre = nombre_completo
        cliente.save(update_fields=['nombre'])

    return cliente


def generar_numero_pedido() -> str:
    """Genera el siguiente número de pedido con formato PED-YYYY-NNNN.

    Toma el último número existente del año, así no se repite aunque
    se hayan borrado pedidos antiguos.
    """
    anio = date.today().year
    prefijo = f'PED-{anio}-'

    ultimo = (
        Pedido.objects
        .filter(numero_pedido__startswith=prefijo)
        .order_by('-numero_pedido')
        .values_list('numero_pedido', flat=True)
        .first()
    )
    siguiente = int(ultimo.rsplit('-', 1)[-1]) + 1 if ultimo else 1
    return f'{prefijo}{siguiente:04d}'