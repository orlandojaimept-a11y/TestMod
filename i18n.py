"""
i18n.py — Internacionalização da Loja Digital

Suporte a 18 idiomas com fallback automático para inglês.
Teclados gerados dinamicamente por idioma.
Regex de botões compilados para aceitar qualquer tradução em qualquer handler.

Idiomas suportados:
  pt, en, es, fr, de, it, ru, uk, zh, ja, ko, ar, tr, pl, nl, sv, ro, hi
"""

import re
import logging
from functools import lru_cache
from typing import Optional

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton

log = logging.getLogger(__name__)

# ── Traduções ─────────────────────────────────────────────────────────────────
# Cada chave corresponde a uma string usada em bot.py via t(lang, key, **kwargs)

_STRINGS: dict[str, dict[str, str]] = {

    # ── Português ─────────────────────────────────────────────────────────────
    "pt": {
        "start": (
            "👋 Bem-vindo à Loja Digital!\n\n"
            "Produtos digitais entregues instantaneamente após o pagamento.\n\n"
            "Usa os botões abaixo para navegar."
        ),
        "help": (
            "ℹ️ Como funciona:\n\n"
            "1. Carrega em 🛒 Produtos\n"
            "2. Clica no link /comprar_<id> do produto que queres\n"
            "3. Envia o pagamento para o endereço indicado\n"
            "4. Recebes o link de download automaticamente aqui\n\n"
            "Dúvidas? Fala connosco."
        ),
        "botmaker": (
            "🤖 Este bot foi desenvolvido por BotMaker.\n\n"
            "Quer um bot personalizado para o seu negócio?\n"
            "Entre em contacto: @BotMakerSupport"
        ),
        "products_header": "📦 Produtos disponíveis:",
        "products_empty":  "😔 Nenhum produto disponível no momento.",
        "order_created": (
            "🧾 Pedido criado!\n\n"
            "Produto: {name}\n\n"
            "Envia exatamente:\n"
            "{amount} {currency}\n\n"
            "Para o endereço:\n"
            "{address}\n\n"
            "⏳ O link de download será enviado aqui assim que o pagamento for confirmado."
        ),
        "payment_confirmed": (
            "✅ Pagamento confirmado!\n\n"
            "Produto: {name}\n\n"
            "🔗 Link de download:\n{link}\n\n"
            "Obrigado pela compra! 🙏"
        ),
        "err_generic":         "❌ Ocorreu um erro. Tenta novamente mais tarde.",
        "err_rate_limit":      "⏳ Demasiados pedidos. Aguarda um momento.",
        "err_product_invalid": "❌ ID de produto inválido.",
        "err_product_notfound":"❌ Produto não encontrado.",
        "err_payment":         "❌ Erro ao gerar pagamento. Tenta mais tarde.",
        "err_access_denied":   "⛔ Acesso negado.",
        "err_order_save": (
            "⚠️ Pagamento criado mas houve um erro interno ao registar o pedido.\n\n"
            "Envia na mesma:\n{amount} {currency}\nPara: {address}\n\n"
            "O teu acesso será ativado assim que o pagamento for detetado."
        ),
        # Botões do teclado
        "btn_products": "🛒 Produtos",
        "btn_help":     "ℹ️ Ajuda",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 Pedidos",
        "btn_add":      "➕ Add produto",
        "btn_remove":   "🗑 Rm produto",
    },

    # ── English ───────────────────────────────────────────────────────────────
    "en": {
        "start": (
            "👋 Welcome to the Digital Store!\n\n"
            "Digital products delivered instantly after payment.\n\n"
            "Use the buttons below to navigate."
        ),
        "help": (
            "ℹ️ How it works:\n\n"
            "1. Tap 🛒 Products\n"
            "2. Click the /buy_<id> link for the product you want\n"
            "3. Send the payment to the given address\n"
            "4. You'll receive the download link here automatically\n\n"
            "Questions? Contact us."
        ),
        "botmaker": (
            "🤖 This bot was developed by BotMaker.\n\n"
            "Want a custom bot for your business?\n"
            "Contact us: @BotMakerSupport"
        ),
        "products_header": "📦 Available products:",
        "products_empty":  "😔 No products available at the moment.",
        "order_created": (
            "🧾 Order created!\n\n"
            "Product: {name}\n\n"
            "Send exactly:\n"
            "{amount} {currency}\n\n"
            "To address:\n"
            "{address}\n\n"
            "⏳ Your download link will be sent here once payment is confirmed."
        ),
        "payment_confirmed": (
            "✅ Payment confirmed!\n\n"
            "Product: {name}\n\n"
            "🔗 Download link:\n{link}\n\n"
            "Thank you for your purchase! 🙏"
        ),
        "err_generic":         "❌ An error occurred. Please try again later.",
        "err_rate_limit":      "⏳ Too many requests. Please wait a moment.",
        "err_product_invalid": "❌ Invalid product ID.",
        "err_product_notfound":"❌ Product not found.",
        "err_payment":         "❌ Payment error. Please try again later.",
        "err_access_denied":   "⛔ Access denied.",
        "err_order_save": (
            "⚠️ Payment created but an internal error occurred while saving your order.\n\n"
            "Please send anyway:\n{amount} {currency}\nTo: {address}\n\n"
            "Your access will be activated once the payment is detected."
        ),
        "btn_products": "🛒 Products",
        "btn_help":     "ℹ️ Help",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 Orders",
        "btn_add":      "➕ Add product",
        "btn_remove":   "🗑 Rm product",
    },

    # ── Español ───────────────────────────────────────────────────────────────
    "es": {
        "start": (
            "👋 ¡Bienvenido a la Tienda Digital!\n\n"
            "Productos digitales entregados al instante tras el pago.\n\n"
            "Usa los botones de abajo para navegar."
        ),
        "help": (
            "ℹ️ Cómo funciona:\n\n"
            "1. Pulsa 🛒 Productos\n"
            "2. Haz clic en el enlace /comprar_<id>\n"
            "3. Envía el pago a la dirección indicada\n"
            "4. Recibirás el enlace de descarga automáticamente\n\n"
            "¿Dudas? Contáctanos."
        ),
        "botmaker": (
            "🤖 Este bot fue desarrollado por BotMaker.\n\n"
            "¿Quieres un bot personalizado?\nContacta: @BotMakerSupport"
        ),
        "products_header": "📦 Productos disponibles:",
        "products_empty":  "😔 No hay productos disponibles en este momento.",
        "order_created": (
            "🧾 ¡Pedido creado!\n\nProducto: {name}\n\n"
            "Envía exactamente:\n{amount} {currency}\n\nA la dirección:\n{address}\n\n"
            "⏳ El enlace de descarga se enviará aquí al confirmarse el pago."
        ),
        "payment_confirmed": (
            "✅ ¡Pago confirmado!\n\nProducto: {name}\n\n"
            "🔗 Enlace de descarga:\n{link}\n\n¡Gracias por tu compra! 🙏"
        ),
        "err_generic":         "❌ Ocurrió un error. Inténtalo más tarde.",
        "err_rate_limit":      "⏳ Demasiadas solicitudes. Espera un momento.",
        "err_product_invalid": "❌ ID de producto inválido.",
        "err_product_notfound":"❌ Producto no encontrado.",
        "err_payment":         "❌ Error al generar el pago. Inténtalo más tarde.",
        "err_access_denied":   "⛔ Acceso denegado.",
        "err_order_save": (
            "⚠️ Pago creado pero ocurrió un error interno.\n\n"
            "Envía de todas formas:\n{amount} {currency}\nA: {address}\n\n"
            "Tu acceso se activará en cuanto se detecte el pago."
        ),
        "btn_products": "🛒 Productos",
        "btn_help":     "ℹ️ Ayuda",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 Pedidos",
        "btn_add":      "➕ Agregar",
        "btn_remove":   "🗑 Eliminar",
    },

    # ── Français ──────────────────────────────────────────────────────────────
    "fr": {
        "start": (
            "👋 Bienvenue sur la Boutique Numérique!\n\n"
            "Produits numériques livrés instantanément après paiement.\n\n"
            "Utilisez les boutons ci-dessous pour naviguer."
        ),
        "help": (
            "ℹ️ Comment ça marche:\n\n"
            "1. Appuyez sur 🛒 Produits\n"
            "2. Cliquez sur /acheter_<id>\n"
            "3. Envoyez le paiement à l'adresse indiquée\n"
            "4. Vous recevrez le lien de téléchargement automatiquement\n\n"
            "Des questions? Contactez-nous."
        ),
        "botmaker": "🤖 Ce bot a été développé par BotMaker.\nContactez: @BotMakerSupport",
        "products_header": "📦 Produits disponibles:",
        "products_empty":  "😔 Aucun produit disponible pour l'instant.",
        "order_created": (
            "🧾 Commande créée!\n\nProduit: {name}\n\n"
            "Envoyez exactement:\n{amount} {currency}\n\nÀ l'adresse:\n{address}\n\n"
            "⏳ Le lien de téléchargement vous sera envoyé dès confirmation du paiement."
        ),
        "payment_confirmed": (
            "✅ Paiement confirmé!\n\nProduit: {name}\n\n"
            "🔗 Lien de téléchargement:\n{link}\n\nMerci pour votre achat! 🙏"
        ),
        "err_generic":         "❌ Une erreur s'est produite. Réessayez plus tard.",
        "err_rate_limit":      "⏳ Trop de requêtes. Attendez un moment.",
        "err_product_invalid": "❌ ID produit invalide.",
        "err_product_notfound":"❌ Produit introuvable.",
        "err_payment":         "❌ Erreur de paiement. Réessayez plus tard.",
        "err_access_denied":   "⛔ Accès refusé.",
        "err_order_save": (
            "⚠️ Paiement créé mais erreur interne.\n\n"
            "Envoyez quand même:\n{amount} {currency}\nÀ: {address}"
        ),
        "btn_products": "🛒 Produits",
        "btn_help":     "ℹ️ Aide",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 Commandes",
        "btn_add":      "➕ Ajouter",
        "btn_remove":   "🗑 Supprimer",
    },

    # ── Deutsch ───────────────────────────────────────────────────────────────
    "de": {
        "start": (
            "👋 Willkommen im Digitalen Shop!\n\n"
            "Digitale Produkte werden sofort nach der Zahlung geliefert.\n\n"
            "Nutze die Schaltflächen unten zur Navigation."
        ),
        "help": (
            "ℹ️ So funktioniert es:\n\n"
            "1. Tippe auf 🛒 Produkte\n"
            "2. Klicke auf /kaufen_<id>\n"
            "3. Sende die Zahlung an die angegebene Adresse\n"
            "4. Du erhältst den Download-Link automatisch hier\n\n"
            "Fragen? Kontaktiere uns."
        ),
        "botmaker": "🤖 Dieser Bot wurde von BotMaker entwickelt.\nKontakt: @BotMakerSupport",
        "products_header": "📦 Verfügbare Produkte:",
        "products_empty":  "😔 Derzeit keine Produkte verfügbar.",
        "order_created": (
            "🧾 Bestellung erstellt!\n\nProdukt: {name}\n\n"
            "Sende genau:\n{amount} {currency}\n\nAn die Adresse:\n{address}\n\n"
            "⏳ Dein Download-Link wird nach Zahlungsbestätigung gesendet."
        ),
        "payment_confirmed": (
            "✅ Zahlung bestätigt!\n\nProdukt: {name}\n\n"
            "🔗 Download-Link:\n{link}\n\nVielen Dank für deinen Kauf! 🙏"
        ),
        "err_generic":         "❌ Ein Fehler ist aufgetreten. Bitte versuche es später.",
        "err_rate_limit":      "⏳ Zu viele Anfragen. Bitte warte einen Moment.",
        "err_product_invalid": "❌ Ungültige Produkt-ID.",
        "err_product_notfound":"❌ Produkt nicht gefunden.",
        "err_payment":         "❌ Zahlungsfehler. Bitte versuche es später.",
        "err_access_denied":   "⛔ Zugriff verweigert.",
        "err_order_save": (
            "⚠️ Zahlung erstellt, aber interner Fehler.\n\n"
            "Sende trotzdem:\n{amount} {currency}\nAn: {address}"
        ),
        "btn_products": "🛒 Produkte",
        "btn_help":     "ℹ️ Hilfe",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 Bestellungen",
        "btn_add":      "➕ Hinzufügen",
        "btn_remove":   "🗑 Entfernen",
    },

    # ── Italiano ──────────────────────────────────────────────────────────────
    "it": {
        "start": (
            "👋 Benvenuto nel Negozio Digitale!\n\n"
            "Prodotti digitali consegnati istantaneamente dopo il pagamento.\n\n"
            "Usa i pulsanti qui sotto per navigare."
        ),
        "help": (
            "ℹ️ Come funziona:\n\n"
            "1. Premi 🛒 Prodotti\n"
            "2. Clicca su /acquista_<id>\n"
            "3. Invia il pagamento all'indirizzo indicato\n"
            "4. Riceverai il link di download automaticamente\n\n"
            "Domande? Contattaci."
        ),
        "botmaker": "🤖 Questo bot è stato sviluppato da BotMaker.\nContatto: @BotMakerSupport",
        "products_header": "📦 Prodotti disponibili:",
        "products_empty":  "😔 Nessun prodotto disponibile al momento.",
        "order_created": (
            "🧾 Ordine creato!\n\nProdotto: {name}\n\n"
            "Invia esattamente:\n{amount} {currency}\n\nAll'indirizzo:\n{address}\n\n"
            "⏳ Il link di download ti verrà inviato alla conferma del pagamento."
        ),
        "payment_confirmed": (
            "✅ Pagamento confermato!\n\nProdotto: {name}\n\n"
            "🔗 Link di download:\n{link}\n\nGrazie per l'acquisto! 🙏"
        ),
        "err_generic":         "❌ Si è verificato un errore. Riprova più tardi.",
        "err_rate_limit":      "⏳ Troppe richieste. Attendi un momento.",
        "err_product_invalid": "❌ ID prodotto non valido.",
        "err_product_notfound":"❌ Prodotto non trovato.",
        "err_payment":         "❌ Errore nel pagamento. Riprova più tardi.",
        "err_access_denied":   "⛔ Accesso negato.",
        "err_order_save": (
            "⚠️ Pagamento creato ma errore interno.\n\n"
            "Invia comunque:\n{amount} {currency}\nA: {address}"
        ),
        "btn_products": "🛒 Prodotti",
        "btn_help":     "ℹ️ Aiuto",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 Ordini",
        "btn_add":      "➕ Aggiungi",
        "btn_remove":   "🗑 Rimuovi",
    },

    # ── Русский ───────────────────────────────────────────────────────────────
    "ru": {
        "start": (
            "👋 Добро пожаловать в Цифровой Магазин!\n\n"
            "Цифровые товары доставляются мгновенно после оплаты.\n\n"
            "Используйте кнопки ниже для навигации."
        ),
        "help": (
            "ℹ️ Как это работает:\n\n"
            "1. Нажмите 🛒 Товары\n"
            "2. Нажмите /купить_<id>\n"
            "3. Отправьте оплату на указанный адрес\n"
            "4. Ссылка для скачивания придёт сюда автоматически\n\n"
            "Вопросы? Свяжитесь с нами."
        ),
        "botmaker": "🤖 Этот бот разработан BotMaker.\nКонтакт: @BotMakerSupport",
        "products_header": "📦 Доступные товары:",
        "products_empty":  "😔 Товары временно недоступны.",
        "order_created": (
            "🧾 Заказ создан!\n\nТовар: {name}\n\n"
            "Отправьте точно:\n{amount} {currency}\n\nНа адрес:\n{address}\n\n"
            "⏳ Ссылка для скачивания будет отправлена после подтверждения оплаты."
        ),
        "payment_confirmed": (
            "✅ Оплата подтверждена!\n\nТовар: {name}\n\n"
            "🔗 Ссылка для скачивания:\n{link}\n\nСпасибо за покупку! 🙏"
        ),
        "err_generic":         "❌ Произошла ошибка. Попробуйте позже.",
        "err_rate_limit":      "⏳ Слишком много запросов. Подождите.",
        "err_product_invalid": "❌ Неверный ID товара.",
        "err_product_notfound":"❌ Товар не найден.",
        "err_payment":         "❌ Ошибка оплаты. Попробуйте позже.",
        "err_access_denied":   "⛔ Доступ запрещён.",
        "err_order_save": (
            "⚠️ Оплата создана, но произошла внутренняя ошибка.\n\n"
            "Всё равно отправьте:\n{amount} {currency}\nНа: {address}"
        ),
        "btn_products": "🛒 Товары",
        "btn_help":     "ℹ️ Помощь",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 Заказы",
        "btn_add":      "➕ Добавить",
        "btn_remove":   "🗑 Удалить",
    },

    # ── Українська ────────────────────────────────────────────────────────────
    "uk": {
        "start": (
            "👋 Ласкаво просимо до Цифрового Магазину!\n\n"
            "Цифрові товари доставляються миттєво після оплати.\n\n"
            "Використовуйте кнопки нижче для навігації."
        ),
        "help": (
            "ℹ️ Як це працює:\n\n"
            "1. Натисніть 🛒 Товари\n"
            "2. Натисніть /купити_<id>\n"
            "3. Надішліть оплату на вказану адресу\n"
            "4. Посилання для завантаження прийде сюди автоматично\n\n"
            "Питання? Зв'яжіться з нами."
        ),
        "botmaker": "🤖 Цей бот розроблений BotMaker.\nКонтакт: @BotMakerSupport",
        "products_header": "📦 Доступні товари:",
        "products_empty":  "😔 Товари тимчасово недоступні.",
        "order_created": (
            "🧾 Замовлення створено!\n\nТовар: {name}\n\n"
            "Надішліть точно:\n{amount} {currency}\n\nНа адресу:\n{address}\n\n"
            "⏳ Посилання для завантаження надійде після підтвердження оплати."
        ),
        "payment_confirmed": (
            "✅ Оплату підтверджено!\n\nТовар: {name}\n\n"
            "🔗 Посилання для завантаження:\n{link}\n\nДякуємо за покупку! 🙏"
        ),
        "err_generic":         "❌ Сталася помилка. Спробуйте пізніше.",
        "err_rate_limit":      "⏳ Забагато запитів. Зачекайте.",
        "err_product_invalid": "❌ Невірний ID товару.",
        "err_product_notfound":"❌ Товар не знайдено.",
        "err_payment":         "❌ Помилка оплати. Спробуйте пізніше.",
        "err_access_denied":   "⛔ Доступ заборонено.",
        "err_order_save": (
            "⚠️ Оплату створено, але стався внутрішній збій.\n\n"
            "Надішліть все одно:\n{amount} {currency}\nНа: {address}"
        ),
        "btn_products": "🛒 Товари",
        "btn_help":     "ℹ️ Допомога",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 Замовлення",
        "btn_add":      "➕ Додати",
        "btn_remove":   "🗑 Видалити",
    },

    # ── 中文 ──────────────────────────────────────────────────────────────────
    "zh": {
        "start": "👋 欢迎来到数字商店！\n\n付款后立即发货。\n\n请使用下方按钮导航。",
        "help": (
            "ℹ️ 使用说明：\n\n"
            "1. 点击 🛒 商品\n2. 点击 /购买_<id>\n"
            "3. 向指定地址发送付款\n4. 确认后自动发送下载链接\n\n如有疑问，请联系我们。"
        ),
        "botmaker": "🤖 本机器人由 BotMaker 开发。\n联系：@BotMakerSupport",
        "products_header": "📦 可用商品：",
        "products_empty":  "😔 暂无可用商品。",
        "order_created": (
            "🧾 订单已创建！\n\n商品：{name}\n\n"
            "请发送：\n{amount} {currency}\n\n到地址：\n{address}\n\n"
            "⏳ 付款确认后，下载链接将自动发送至此处。"
        ),
        "payment_confirmed": "✅ 付款已确认！\n\n商品：{name}\n\n🔗 下载链接：\n{link}\n\n感谢您的购买！🙏",
        "err_generic":         "❌ 发生错误，请稍后重试。",
        "err_rate_limit":      "⏳ 请求过多，请稍候。",
        "err_product_invalid": "❌ 无效的商品ID。",
        "err_product_notfound":"❌ 未找到商品。",
        "err_payment":         "❌ 支付错误，请稍后重试。",
        "err_access_denied":   "⛔ 访问被拒绝。",
        "err_order_save":      "⚠️ 付款已创建但内部错误。\n\n仍请发送：\n{amount} {currency}\n到：{address}",
        "btn_products": "🛒 商品",
        "btn_help":     "ℹ️ 帮助",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 订单",
        "btn_add":      "➕ 添加",
        "btn_remove":   "🗑 删除",
    },

    # ── 日本語 ────────────────────────────────────────────────────────────────
    "ja": {
        "start": "👋 デジタルストアへようこそ！\n\n支払い後すぐにデジタル商品をお届けします。\n\n下のボタンをご利用ください。",
        "help": (
            "ℹ️ ご利用方法：\n\n"
            "1. 🛒 商品をタップ\n2. /購入_<id> をクリック\n"
            "3. 表示されたアドレスに送金\n4. 確認後、ダウンロードリンクをお送りします\n\nご質問はお気軽に。"
        ),
        "botmaker": "🤖 このボットはBotMakerが開発しました。\nお問い合わせ：@BotMakerSupport",
        "products_header": "📦 利用可能な商品：",
        "products_empty":  "😔 現在利用可能な商品はありません。",
        "order_created": (
            "🧾 注文が作成されました！\n\n商品：{name}\n\n"
            "正確に送金してください：\n{amount} {currency}\n\nアドレス：\n{address}\n\n"
            "⏳ 支払い確認後、ダウンロードリンクをお送りします。"
        ),
        "payment_confirmed": "✅ 支払いが確認されました！\n\n商品：{name}\n\n🔗 ダウンロードリンク：\n{link}\n\nご購入ありがとうございます！🙏",
        "err_generic":         "❌ エラーが発生しました。後でお試しください。",
        "err_rate_limit":      "⏳ リクエストが多すぎます。少々お待ちください。",
        "err_product_invalid": "❌ 無効な商品IDです。",
        "err_product_notfound":"❌ 商品が見つかりません。",
        "err_payment":         "❌ 支払いエラー。後でお試しください。",
        "err_access_denied":   "⛔ アクセスが拒否されました。",
        "err_order_save":      "⚠️ 支払いは作成されましたが内部エラーが発生しました。\n\n送金してください：\n{amount} {currency}\n宛先：{address}",
        "btn_products": "🛒 商品",
        "btn_help":     "ℹ️ ヘルプ",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 注文",
        "btn_add":      "➕ 追加",
        "btn_remove":   "🗑 削除",
    },

    # ── 한국어 ────────────────────────────────────────────────────────────────
    "ko": {
        "start": "👋 디지털 스토어에 오신 것을 환영합니다!\n\n결제 후 즉시 디지털 상품이 전달됩니다.\n\n아래 버튼을 사용하여 탐색하세요.",
        "help": (
            "ℹ️ 이용 방법：\n\n"
            "1. 🛒 상품을 탭하세요\n2. /구매_<id>를 클릭하세요\n"
            "3. 안내된 주소로 결제를 보내세요\n4. 확인 후 다운로드 링크가 자동으로 전송됩니다\n\n문의사항이 있으신가요? 연락해 주세요."
        ),
        "botmaker": "🤖 이 봇은 BotMaker가 개발했습니다.\n연락처: @BotMakerSupport",
        "products_header": "📦 이용 가능한 상품：",
        "products_empty":  "😔 현재 이용 가능한 상품이 없습니다.",
        "order_created": (
            "🧾 주문이 생성되었습니다!\n\n상품: {name}\n\n"
            "정확히 보내주세요：\n{amount} {currency}\n\n주소：\n{address}\n\n"
            "⏳ 결제 확인 후 다운로드 링크가 전송됩니다."
        ),
        "payment_confirmed": "✅ 결제가 확인되었습니다!\n\n상품: {name}\n\n🔗 다운로드 링크：\n{link}\n\n구매해 주셔서 감사합니다! 🙏",
        "err_generic":         "❌ 오류가 발생했습니다. 나중에 다시 시도해 주세요.",
        "err_rate_limit":      "⏳ 요청이 너무 많습니다. 잠시 기다려 주세요.",
        "err_product_invalid": "❌ 유효하지 않은 상품 ID입니다.",
        "err_product_notfound":"❌ 상품을 찾을 수 없습니다.",
        "err_payment":         "❌ 결제 오류. 나중에 다시 시도해 주세요.",
        "err_access_denied":   "⛔ 접근이 거부되었습니다.",
        "err_order_save":      "⚠️ 결제는 생성됐지만 내부 오류가 발생했습니다.\n\n보내주세요：\n{amount} {currency}\n주소: {address}",
        "btn_products": "🛒 상품",
        "btn_help":     "ℹ️ 도움말",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 주문",
        "btn_add":      "➕ 추가",
        "btn_remove":   "🗑 삭제",
    },

    # ── العربية ───────────────────────────────────────────────────────────────
    "ar": {
        "start": "👋 مرحبًا بك في المتجر الرقمي!\n\nيتم تسليم المنتجات الرقمية فورًا بعد الدفع.\n\nاستخدم الأزرار أدناه للتنقل.",
        "help": (
            "ℹ️ كيف يعمل:\n\n"
            "1. اضغط على 🛒 المنتجات\n2. انقر على /شراء_<id>\n"
            "3. أرسل الدفع إلى العنوان المحدد\n4. ستصلك رابط التنزيل تلقائيًا\n\nأسئلة؟ تواصل معنا."
        ),
        "botmaker": "🤖 تم تطوير هذا البوت بواسطة BotMaker.\nللتواصل: @BotMakerSupport",
        "products_header": "📦 المنتجات المتاحة:",
        "products_empty":  "😔 لا توجد منتجات متاحة حاليًا.",
        "order_created": (
            "🧾 تم إنشاء الطلب!\n\nالمنتج: {name}\n\n"
            "أرسل بالضبط:\n{amount} {currency}\n\nإلى العنوان:\n{address}\n\n"
            "⏳ سيتم إرسال رابط التنزيل هنا بعد تأكيد الدفع."
        ),
        "payment_confirmed": "✅ تم تأكيد الدفع!\n\nالمنتج: {name}\n\n🔗 رابط التنزيل:\n{link}\n\nشكرًا لشرائك! 🙏",
        "err_generic":         "❌ حدث خطأ. حاول مرة أخرى لاحقًا.",
        "err_rate_limit":      "⏳ طلبات كثيرة جدًا. انتظر لحظة.",
        "err_product_invalid": "❌ معرّف المنتج غير صالح.",
        "err_product_notfound":"❌ المنتج غير موجود.",
        "err_payment":         "❌ خطأ في الدفع. حاول مرة أخرى لاحقًا.",
        "err_access_denied":   "⛔ تم رفض الوصول.",
        "err_order_save":      "⚠️ تم إنشاء الدفع لكن حدث خطأ داخلي.\n\nأرسل على أي حال:\n{amount} {currency}\nإلى: {address}",
        "btn_products": "🛒 المنتجات",
        "btn_help":     "ℹ️ مساعدة",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 الطلبات",
        "btn_add":      "➕ إضافة",
        "btn_remove":   "🗑 حذف",
    },

    # ── Türkçe ────────────────────────────────────────────────────────────────
    "tr": {
        "start": "👋 Dijital Mağazaya Hoş Geldiniz!\n\nÖdeme sonrası dijital ürünler anında teslim edilir.\n\nGezinmek için aşağıdaki düğmeleri kullanın.",
        "help": (
            "ℹ️ Nasıl çalışır:\n\n"
            "1. 🛒 Ürünler'e dokun\n2. /satin_al_<id> bağlantısına tıkla\n"
            "3. Belirtilen adrese ödeme gönder\n4. Onaylandıktan sonra indirme bağlantısı otomatik gönderilir\n\nSorularınız mı var? Bize ulaşın."
        ),
        "botmaker": "🤖 Bu bot BotMaker tarafından geliştirildi.\nİletişim: @BotMakerSupport",
        "products_header": "📦 Mevcut ürünler:",
        "products_empty":  "😔 Şu anda mevcut ürün yok.",
        "order_created": (
            "🧾 Sipariş oluşturuldu!\n\nÜrün: {name}\n\n"
            "Tam olarak gönderin:\n{amount} {currency}\n\nAdrese:\n{address}\n\n"
            "⏳ Ödeme onaylandıktan sonra indirme bağlantısı burada göönderilecek."
        ),
        "payment_confirmed": "✅ Ödeme onaylandı!\n\nÜrün: {name}\n\n🔗 İndirme bağlantısı:\n{link}\n\nAlışverişiniz için teşekkürler! 🙏",
        "err_generic":         "❌ Bir hata oluştu. Daha sonra tekrar deneyin.",
        "err_rate_limit":      "⏳ Çok fazla istek. Lütfen bekleyin.",
        "err_product_invalid": "❌ Geçersiz ürün ID.",
        "err_product_notfound":"❌ Ürün bulunamadı.",
        "err_payment":         "❌ Ödeme hatası. Daha sonra deneyin.",
        "err_access_denied":   "⛔ Erişim reddedildi.",
        "err_order_save":      "⚠️ Ödeme oluşturuldu ama dahili hata var.\n\nYine de gönderin:\n{amount} {currency}\nAdres: {address}",
        "btn_products": "🛒 Ürünler",
        "btn_help":     "ℹ️ Yardım",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 Siparişler",
        "btn_add":      "➕ Ekle",
        "btn_remove":   "🗑 Kaldır",
    },

    # ── Polski ────────────────────────────────────────────────────────────────
    "pl": {
        "start": "👋 Witaj w Cyfrowym Sklepie!\n\nProdukty cyfrowe dostarczane natychmiast po płatności.\n\nUżyj przycisków poniżej do nawigacji.",
        "help": (
            "ℹ️ Jak to działa:\n\n"
            "1. Dotknij 🛒 Produkty\n2. Kliknij /kup_<id>\n"
            "3. Wyślij płatność na podany adres\n4. Link do pobrania przyjdzie tu automatycznie\n\nPytania? Skontaktuj się z nami."
        ),
        "botmaker": "🤖 Ten bot został stworzony przez BotMaker.\nKontakt: @BotMakerSupport",
        "products_header": "📦 Dostępne produkty:",
        "products_empty":  "😔 Brak dostępnych produktów.",
        "order_created": (
            "🧾 Zamówienie utworzone!\n\nProdukt: {name}\n\n"
            "Wyślij dokładnie:\n{amount} {currency}\n\nNa adres:\n{address}\n\n"
            "⏳ Link do pobrania zostanie wysłany po potwierdzeniu płatności."
        ),
        "payment_confirmed": "✅ Płatność potwierdzona!\n\nProdukt: {name}\n\n🔗 Link do pobrania:\n{link}\n\nDziękujemy za zakup! 🙏",
        "err_generic":         "❌ Wystąpił błąd. Spróbuj ponownie później.",
        "err_rate_limit":      "⏳ Zbyt wiele żądań. Poczekaj chwilę.",
        "err_product_invalid": "❌ Nieprawidłowe ID produktu.",
        "err_product_notfound":"❌ Produkt nie znaleziony.",
        "err_payment":         "❌ Błąd płatności. Spróbuj ponownie później.",
        "err_access_denied":   "⛔ Dostęp zabroniony.",
        "err_order_save":      "⚠️ Płatność utworzona, ale błąd wewnętrzny.\n\nWyślij i tak:\n{amount} {currency}\nNa: {address}",
        "btn_products": "🛒 Produkty",
        "btn_help":     "ℹ️ Pomoc",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 Zamówienia",
        "btn_add":      "➕ Dodaj",
        "btn_remove":   "🗑 Usuń",
    },

    # ── Nederlands ────────────────────────────────────────────────────────────
    "nl": {
        "start": "👋 Welkom bij de Digitale Winkel!\n\nDigitale producten worden direct geleverd na betaling.\n\nGebruik de knoppen hieronder om te navigeren.",
        "help": (
            "ℹ️ Hoe het werkt:\n\n"
            "1. Tik op 🛒 Producten\n2. Klik op /kopen_<id>\n"
            "3. Stuur de betaling naar het opgegeven adres\n4. De downloadlink wordt hier automatisch gestuurd\n\nVragen? Neem contact op."
        ),
        "botmaker": "🤖 Deze bot is ontwikkeld door BotMaker.\nContact: @BotMakerSupport",
        "products_header": "📦 Beschikbare producten:",
        "products_empty":  "😔 Momenteel geen producten beschikbaar.",
        "order_created": (
            "🧾 Bestelling aangemaakt!\n\nProduct: {name}\n\n"
            "Stuur precies:\n{amount} {currency}\n\nNaar adres:\n{address}\n\n"
            "⏳ De downloadlink wordt hier gestuurd na betalingsbevestiging."
        ),
        "payment_confirmed": "✅ Betaling bevestigd!\n\nProduct: {name}\n\n🔗 Downloadlink:\n{link}\n\nBedankt voor je aankoop! 🙏",
        "err_generic":         "❌ Er is een fout opgetreden. Probeer het later opnieuw.",
        "err_rate_limit":      "⏳ Te veel verzoeken. Even wachten.",
        "err_product_invalid": "❌ Ongeldig product ID.",
        "err_product_notfound":"❌ Product niet gevonden.",
        "err_payment":         "❌ Betalingsfout. Probeer het later opnieuw.",
        "err_access_denied":   "⛔ Toegang geweigerd.",
        "err_order_save":      "⚠️ Betaling aangemaakt maar interne fout.\n\nStuur toch:\n{amount} {currency}\nNaar: {address}",
        "btn_products": "🛒 Producten",
        "btn_help":     "ℹ️ Help",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 Bestellingen",
        "btn_add":      "➕ Toevoegen",
        "btn_remove":   "🗑 Verwijderen",
    },

    # ── Svenska ───────────────────────────────────────────────────────────────
    "sv": {
        "start": "👋 Välkommen till Digital Butik!\n\nDigitala produkter levereras omedelbart efter betalning.\n\nAnvänd knapparna nedan för att navigera.",
        "help": (
            "ℹ️ Så här fungerar det:\n\n"
            "1. Tryck på 🛒 Produkter\n2. Klicka på /köp_<id>\n"
            "3. Skicka betalning till angiven adress\n4. Nedladdningslänken skickas hit automatiskt\n\nFrågor? Kontakta oss."
        ),
        "botmaker": "🤖 Den här boten utvecklades av BotMaker.\nKontakt: @BotMakerSupport",
        "products_header": "📦 Tillgängliga produkter:",
        "products_empty":  "😔 Inga produkter tillgängliga för tillfället.",
        "order_created": (
            "🧾 Beställning skapad!\n\nProdukt: {name}\n\n"
            "Skicka exakt:\n{amount} {currency}\n\nTill adress:\n{address}\n\n"
            "⏳ Nedladdningslänken skickas hit när betalningen bekräftats."
        ),
        "payment_confirmed": "✅ Betalning bekräftad!\n\nProdukt: {name}\n\n🔗 Nedladdningslänk:\n{link}\n\nTack för ditt köp! 🙏",
        "err_generic":         "❌ Ett fel uppstod. Försök igen senare.",
        "err_rate_limit":      "⏳ För många förfrågningar. Vänta lite.",
        "err_product_invalid": "❌ Ogiltigt produkt-ID.",
        "err_product_notfound":"❌ Produkten hittades inte.",
        "err_payment":         "❌ Betalningsfel. Försök igen senare.",
        "err_access_denied":   "⛔ Åtkomst nekad.",
        "err_order_save":      "⚠️ Betalning skapad men internt fel.\n\nSkicka ändå:\n{amount} {currency}\nTill: {address}",
        "btn_products": "🛒 Produkter",
        "btn_help":     "ℹ️ Hjälp",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 Beställningar",
        "btn_add":      "➕ Lägg till",
        "btn_remove":   "🗑 Ta bort",
    },

    # ── Română ────────────────────────────────────────────────────────────────
    "ro": {
        "start": "👋 Bine ai venit la Magazinul Digital!\n\nProdusele digitale sunt livrate instant după plată.\n\nFolosește butoanele de mai jos pentru navigare.",
        "help": (
            "ℹ️ Cum funcționează:\n\n"
            "1. Apasă 🛒 Produse\n2. Dă click pe /cumpara_<id>\n"
            "3. Trimite plata la adresa indicată\n4. Link-ul de descărcare va fi trimis automat\n\nÎntrebări? Contactează-ne."
        ),
        "botmaker": "🤖 Acest bot a fost dezvoltat de BotMaker.\nContact: @BotMakerSupport",
        "products_header": "📦 Produse disponibile:",
        "products_empty":  "😔 Niciun produs disponibil momentan.",
        "order_created": (
            "🧾 Comandă creată!\n\nProdus: {name}\n\n"
            "Trimite exact:\n{amount} {currency}\n\nLa adresa:\n{address}\n\n"
            "⏳ Link-ul de descărcare va fi trimis după confirmarea plății."
        ),
        "payment_confirmed": "✅ Plată confirmată!\n\nProdus: {name}\n\n🔗 Link descărcare:\n{link}\n\nMulțumim pentru achiziție! 🙏",
        "err_generic":         "❌ A apărut o eroare. Încearcă mai târziu.",
        "err_rate_limit":      "⏳ Prea multe cereri. Așteaptă un moment.",
        "err_product_invalid": "❌ ID produs invalid.",
        "err_product_notfound":"❌ Produs negăsit.",
        "err_payment":         "❌ Eroare la plată. Încearcă mai târziu.",
        "err_access_denied":   "⛔ Acces refuzat.",
        "err_order_save":      "⚠️ Plata creată dar eroare internă.\n\nTrimite oricum:\n{amount} {currency}\nLa: {address}",
        "btn_products": "🛒 Produse",
        "btn_help":     "ℹ️ Ajutor",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 Comenzi",
        "btn_add":      "➕ Adaugă",
        "btn_remove":   "🗑 Șterge",
    },

    # ── हिन्दी ────────────────────────────────────────────────────────────────
    "hi": {
        "start": "👋 डिजिटल स्टोर में आपका स्वागत है!\n\nभुगतान के बाद तुरंत डिजिटल उत्पाद डिलीवर किए जाते हैं।\n\nनेविगेट करने के लिए नीचे दिए बटनों का उपयोग करें।",
        "help": (
            "ℹ️ यह कैसे काम करता है:\n\n"
            "1. 🛒 उत्पाद पर टैप करें\n2. /खरीदें_<id> पर क्लिक करें\n"
            "3. बताए गए पते पर भुगतान भेजें\n4. पुष्टि के बाद डाउनलोड लिंक यहाँ आएगा\n\nप्रश्न? हमसे संपर्क करें।"
        ),
        "botmaker": "🤖 यह बॉट BotMaker द्वारा विकसित किया गया है।\nसंपर्क: @BotMakerSupport",
        "products_header": "📦 उपलब्ध उत्पाद:",
        "products_empty":  "😔 अभी कोई उत्पाद उपलब्ध नहीं है।",
        "order_created": (
            "🧾 ऑर्डर बनाया गया!\n\nउत्पाद: {name}\n\n"
            "बिल्कुल भेजें:\n{amount} {currency}\n\nपते पर:\n{address}\n\n"
            "⏳ भुगतान की पुष्टि होने पर डाउनलोड लिंक यहाँ भेजा जाएगा।"
        ),
        "payment_confirmed": "✅ भुगतान की पुष्टि हुई!\n\nउत्पाद: {name}\n\n🔗 डाउनलोड लिंक:\n{link}\n\nखरीद के लिए धन्यवाद! 🙏",
        "err_generic":         "❌ एक त्रुटि हुई। बाद में पुनः प्रयास करें।",
        "err_rate_limit":      "⏳ बहुत अधिक अनुरोध। कृपया प्रतीक्षा करें।",
        "err_product_invalid": "❌ अमान्य उत्पाद ID।",
        "err_product_notfound":"❌ उत्पाद नहीं मिला।",
        "err_payment":         "❌ भुगतान त्रुटि। बाद में पुनः प्रयास करें।",
        "err_access_denied":   "⛔ पहुँच अस्वीकृत।",
        "err_order_save":      "⚠️ भुगतान बनाया गया लेकिन आंतरिक त्रुटि।\n\nफिर भी भेजें:\n{amount} {currency}\nपते: {address}",
        "btn_products": "🛒 उत्पाद",
        "btn_help":     "ℹ️ सहायता",
        "btn_botmaker": "🤖 BotMaker",
        "btn_orders":   "📋 ऑर्डर",
        "btn_add":      "➕ जोड़ें",
        "btn_remove":   "🗑 हटाएं",
    },
}

# Fallback padrão
_DEFAULT_LANG = "en"

# Mapeamento: prefixo de 2 letras → idioma suportado
_LANG_MAP: dict[str, str] = {
    "pt": "pt", "en": "en", "es": "es", "fr": "fr",
    "de": "de", "it": "it", "ru": "ru", "uk": "uk",
    "zh": "zh", "ja": "ja", "ko": "ko", "ar": "ar",
    "tr": "tr", "pl": "pl", "nl": "nl", "sv": "sv",
    "ro": "ro", "hi": "hi",
}


# ── API pública ───────────────────────────────────────────────────────────────

def get_lang(update: Update) -> str:
    """
    Devolve o código de idioma do utilizador (2 letras), com fallback para inglês.
    Lê update.effective_user.language_code (ex: 'pt-BR', 'en', 'zh-hans').
    """
    try:
        code = (update.effective_user.language_code or "").lower()
        prefix = code[:2]
        return _LANG_MAP.get(prefix, _DEFAULT_LANG)
    except Exception:
        return _DEFAULT_LANG


def t(lang: str, key: str, **kwargs) -> str:
    """
    Devolve a string traduzida para o idioma dado, com fallback para inglês.
    Suporta formatação via kwargs: t('pt', 'order_created', name='X', amount=1.5, ...)
    """
    strings = _STRINGS.get(lang) or _STRINGS[_DEFAULT_LANG]
    template = strings.get(key) or _STRINGS[_DEFAULT_LANG].get(key, f"[{key}]")
    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError as e:
            log.warning(f"i18n: chave de formatação em falta: {e} (lang={lang}, key={key})")
            return template
    return template


def _btn(lang: str, key: str) -> str:
    """Devolve o texto de um botão para o idioma dado."""
    return t(lang, key)


@lru_cache(maxsize=32)
def make_main_kb(lang: str) -> ReplyKeyboardMarkup:
    """Teclado principal (utilizadores normais). Cacheado por idioma."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(_btn(lang, "btn_products")), KeyboardButton(_btn(lang, "btn_help"))],
            [KeyboardButton(_btn(lang, "btn_botmaker"))],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


@lru_cache(maxsize=8)
def make_admin_kb(lang: str) -> ReplyKeyboardMarkup:
    """Teclado de administrador. Cacheado por idioma."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(_btn(lang, "btn_products")),  KeyboardButton(_btn(lang, "btn_orders"))],
            [KeyboardButton(_btn(lang, "btn_add")),       KeyboardButton(_btn(lang, "btn_remove"))],
            [KeyboardButton(_btn(lang, "btn_help")),      KeyboardButton(_btn(lang, "btn_botmaker"))],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# ── Regex de botões (para MessageHandler) ────────────────────────────────────
# Cada RE aceita o texto do botão em QUALQUER idioma suportado.
# Usado em bot.py com: filters.Regex(f"^({BTN_PRODUCTS_RE})$")

def _build_btn_re(btn_key: str) -> str:
    """Constrói um regex que aceita o texto de um botão em todos os idiomas."""
    texts = set()
    for lang_strings in _STRINGS.values():
        text = lang_strings.get(btn_key, "")
        if text:
            texts.add(re.escape(text))
    return "|".join(sorted(texts))


BTN_PRODUCTS_RE = _build_btn_re("btn_products")
BTN_HELP_RE     = _build_btn_re("btn_help")
BTN_BOTMAKER_RE = _build_btn_re("btn_botmaker")
BTN_ORDERS_RE   = _build_btn_re("btn_orders")
BTN_ADD_RE      = _build_btn_re("btn_add")
BTN_REMOVE_RE   = _build_btn_re("btn_remove")
