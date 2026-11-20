from django.test.utils import override_settings

with override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend'
):
    from ventas.tasks import enviar_confirmacion_pedido
    from ventas.models import Pedido

    # Tomar un pedido existente
    pedido = Pedido.objects.filter(estado='pagado').first()
    if pedido:
        resultado = enviar_confirmacion_pedido.delay(pedido.pk)
        print('Resultado:', resultado.get())
    else:
        print('No hay pedidos pagados. Crea uno en /catalogo/checkout/')
