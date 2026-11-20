# catalogo/webhook_views.py
"""Webhook de Stripe — W15 + W16.

Recibe eventos de Stripe y actualiza el estado del Pedido:
    payment_intent.succeeded      → pedido 'pagado', stock descontado
                                    y tarea de confirmación encolada (W16).
    payment_intent.payment_failed → pedido 'cancelado'.

La firma se verifica con STRIPE_WEBHOOK_SECRET. El procesamiento es
idempotente: solo actúa si el pedido sigue en 'pendiente'.
"""
import logging

import stripe
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from productos.models import Producto
from ventas.models import Pedido
from ventas.tasks import enviar_confirmacion_pedido   # W16

logger = logging.getLogger(__name__)


def _a_dict(obj):
    """Convierte un StripeObject en dict; deja pasar los dict tal cual."""
    if isinstance(obj, dict):
        return obj
    return obj.to_dict()


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Procesa eventos de Stripe. Stripe no envía CSRF, por eso es csrf_exempt."""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except ValueError:
        logger.warning('Webhook: payload inválido recibido.')
        return HttpResponseBadRequest('Payload inválido.')
    except stripe.SignatureVerificationError:
        logger.warning('Webhook: firma inválida — posible ataque.')
        return HttpResponseBadRequest('Firma inválida.')

    intent = _a_dict(event['data']['object'])
    pedido_id = (intent.get('metadata') or {}).get('pedido_id')

    if not pedido_id:
        return HttpResponse(status=200)

    if event['type'] == 'payment_intent.succeeded':
        pedido_confirmado_id = None

        with transaction.atomic():
            pedido = (
                Pedido.objects.select_for_update()
                .filter(pk=pedido_id, estado='pendiente')
                .first()
            )
            if pedido:
                for item in pedido.items_snapshot:
                    Producto.objects.filter(pk=item['producto_id']).update(
                        stock=F('stock') - int(item['cantidad'])
                    )
                pedido.estado = 'pagado'
                pedido.save(update_fields=['estado'])
                pedido_confirmado_id = pedido.pk

        # W16: se encola FUERA de la transacción, cuando el pago ya quedó
        # guardado. Si Redis falla, se registra el error pero Stripe recibe
        # 200 (si respondiera 500, Stripe reintentaría el webhook).
        if pedido_confirmado_id is not None:
            try:
                enviar_confirmacion_pedido.delay(pedido_confirmado_id)
            except Exception:
                logger.exception(
                    f'No se pudo encolar la confirmación del pedido '
                    f'{pedido_confirmado_id}'
                )

    elif event['type'] == 'payment_intent.payment_failed':
        Pedido.objects.filter(pk=pedido_id, estado='pendiente').update(
            estado='cancelado'
        )

    return HttpResponse(status=200)