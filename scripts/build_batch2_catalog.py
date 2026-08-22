#!/usr/bin/env python3
"""Generate integration_catalog_batch2.py from compact plugin specs."""

from __future__ import annotations

from pathlib import Path
from textwrap import indent

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "integration_catalog_batch2.py"

SECURITY_STEPS = [
    "Store API keys only in this encrypted vault — never in email, chat, or public repos.",
    "Use sandbox / test keys first; switch to live keys only after owner verification is complete.",
    "Restrict API keys to the minimum scopes (payments or read-reviews only).",
    "Rotate keys if a staff member with access leaves the business.",
]

# slug, name, provider, description, regions, category, links[(label,url)], domain, color, initial, simple_icon|None
SPECS: list[tuple] = [
    # HK / MO / TW payments
    ("tap_and_go", "Tap & Go", "octopus", "Octopus Tap & Go — HK transit wallet checkout", ("hk",), "payment",
     [("Tap & Go merchant", "https://www.octopus.com.hk/en/merchant/tap-and-go/index.html")],
     "octopus.com.hk", "F68B1F", "TG", None),
    ("macau_pass", "Macau Pass", "macau_pass", "Macau Pass stored-value payments", ("mo",), "payment",
     [("Macau Pass", "https://www.macau-pass.com/")], "macau-pass.com", "E31C23", "MP", None),
    ("bnu_pay", "BNU Pay", "bnu", "BNU / 丰付宝 — Macau mobile wallet", ("mo",), "payment",
     [("BNU Card merchant", "https://www.bnucard.com/")], "bnucard.com", "C8102E", "BNU", None),
    ("boc_pay", "BoC Pay", "boc", "Bank of China Smart Pay — HK bank wallet", ("hk",), "payment",
     [("BoC Pay", "https://www.bochk.com/")], "bochk.com", "C8102E", "BoC", None),
    ("icash_pay", "icash Pay", "icash", "Taiwan icash Pay e-wallet checkout", ("tw",), "payment",
     [("icash Pay merchant", "https://www.icashpay.com.tw/")], "icashpay.com.tw", "00A651", "ic", None),
    ("pi_wallet", "Pi Wallet", "pi", "Taiwan Pi 拍钱包 mobile payments", ("tw",), "payment",
     [("Pi Wallet business", "https://www.piwallet.com.tw/")], "piwallet.com.tw", "F5B041", "π", None),
    ("pxpay_plus", "PXPay Plus", "pxpay", "Taiwan 全支付 PXPay Plus checkout", ("tw",), "payment",
     [("PXPay Plus", "https://www.pxpayplus.com/")], "pxpayplus.com", "00B140", "PX", None),
    # SEA payments
    ("paynow", "PayNow", "paynow", "Singapore PayNow QR / bank transfer", ("sea",), "payment",
     [("PayNow for businesses", "https://www.abs.org.sg/consumer-banking/paynow")], "abs.org.sg", "7D2E8D", "PN", None),
    ("favepay", "FavePay", "fave", "FavePay — SG / MY lifestyle wallet", ("sea",), "payment",
     [("Fave for Business", "https://business.fave.com/")], "fave.com", "DE206A", "F", "fave"),
    ("boost", "Boost", "boost", "Boost e-wallet — Malaysia", ("sea",), "payment",
     [("Boost Business", "https://www.myboost.com.my/business")], "myboost.com.my", "E82227", "B", None),
    ("dana", "Dana", "dana", "Indonesia Dana e-wallet checkout", ("sea",), "payment",
     [("Dana Bisnis", "https://www.dana.id/business")], "dana.id", "108EE9", "D", "dana"),
    ("ovo", "OVO", "ovo", "Indonesia OVO wallet payments", ("sea",), "payment",
     [("OVO for Business", "https://www.ovo.id/business")], "ovo.id", "4C3494", "O", None),
    ("gopay", "GoPay", "gopay", "Indonesia GoPay merchant checkout", ("sea",), "payment",
     [("GoPay Merchant", "https://www.gojek.com/gopaymerchant/")], "gojek.com", "00AA13", "Go", "gojek"),
    ("linkaja", "LinkAja", "linkaja", "Indonesia LinkAja digital payments", ("sea",), "payment",
     [("LinkAja Business", "https://www.linkaja.id/en/business")], "linkaja.id", "E72527", "L", None),
    ("qris", "QRIS", "qris", "Indonesia QRIS unified QR standard", ("sea",), "payment",
     [("QRIS — Bank Indonesia", "https://www.bi.go.id/en/fungsi-utama/sistem-pembayaran/qris/default.aspx")], "bi.go.id", "ED1C24", "QR", None),
    ("coins_ph", "Coins.ph", "coins", "Philippines Coins.ph crypto & wallet checkout", ("sea",), "payment",
     [("Coins.ph Business", "https://www.coins.ph/business")], "coins.ph", "0057FF", "C", None),
    ("dragonpay", "Dragonpay", "dragonpay", "Philippines Dragonpay online payments", ("sea",), "payment",
     [("Dragonpay merchant", "https://www.dragonpay.ph/")], "dragonpay.ph", "F7941D", "D", None),
    ("paymongo", "PayMongo", "paymongo", "Philippines PayMongo online checkout", ("sea",), "payment",
     [("PayMongo merchant", "https://www.paymongo.com/")], "paymongo.com", "6B46C1", "PM", None),
    ("billplz", "Billplz", "billplz", "Malaysia Billplz payment collections", ("sea",), "payment",
     [("Billplz", "https://www.billplz.com/")], "billplz.com", "0ABAB5", "B", None),
    ("rabbit_line_pay", "Rabbit LINE Pay", "rabbit", "Thailand Rabbit LINE Pay wallet", ("sea",), "payment",
     [("Rabbit merchant", "https://rabbit.co.th/business")], "rabbit.co.th", "00B900", "R", "line"),
    ("scb_easy", "SCB Easy", "scb", "Thailand SCB Easy / K PLUS bank payments", ("sea",), "payment",
     [("SCB Easy", "https://www.scb.co.th/en/personal-banking/digital-banking/scb-easy.html")], "scb.co.th", "4E2A84", "SCB", None),
    ("vietqr", "VietQR", "vietqr", "Vietnam VietQR / Napas instant transfer", ("sea",), "payment",
     [("VietQR — Napas", "https://napas.com.vn/vietqr")], "napas.com.vn", "006B3F", "VQ", None),
    ("viettel_money", "Viettel Money", "viettel", "Vietnam Viettel Money wallet", ("sea",), "payment",
     [("Viettel Money business", "https://viettelmoney.vn/")], "viettelmoney.vn", "EE0033", "VT", None),
    ("vnpay", "VNPay", "vnpay", "Vietnam VNPay gateway & QR checkout", ("sea",), "payment",
     [("VNPay merchant", "https://vnpay.vn/")], "vnpay.vn", "0054A6", "VN", None),
    ("bakong", "Bakong", "bakong", "Cambodia Bakong digital riel payments", ("sea",), "payment",
     [("Bakong — NBC", "https://bakong.nbc.gov.kh/")], "nbc.gov.kh", "003DA5", "BK", None),
    ("wave_money", "Wave Money", "wave", "Myanmar Wave Money mobile wallet", ("sea",), "payment",
     [("Wave Money business", "https://wavemoney.com.mm/")], "wavemoney.com.mm", "F5A800", "W", None),
    # JP / KR
    ("paidy", "Paidy", "paidy", "Japan Paidy buy-now-pay-later checkout", ("jp",), "payment",
     [("Paidy merchant", "https://paidy.com/merchant/")], "paidy.com", "FF009C", "P", "paidy"),
    ("line_pay_tw", "LINE Pay Taiwan", "line", "Taiwan LINE Pay wallet checkout", ("tw",), "payment",
     [("LINE Pay TW merchant", "https://pay.line.me/tw/merchant")], "line.me", "00C300", "L", "line"),
    ("samsung_pay", "Samsung Pay", "samsung", "Korea Samsung Pay — via payment gateway", ("kr",), "payment",
     [("Samsung Pay merchant docs", "https://developer.samsung.com/pay")], "samsung.com", "1428A0", "S", "samsungpay"),
    ("payco", "PAYCO", "payco", "Korea PAYCO wallet & checkout", ("kr",), "payment",
     [("PAYCO partner", "https://www.payco.com/partner")], "payco.com", "FA2828", "P", None),
    ("smilepay", "SmilePay", "smilepay", "Korea SmilePay hosted checkout", ("kr",), "payment",
     [("SmilePay merchant", "https://www.mysmilepay.com/")], "mysmilepay.com", "FF6B00", "S", None),
    # India / South Asia
    ("phonepe", "PhonePe", "phonepe", "India PhonePe UPI & wallet checkout", ("global",), "payment",
     [("PhonePe Business", "https://business.phonepe.com/")], "phonepe.com", "5F259F", "Pe", "phonepe"),
    ("paytm", "Paytm", "paytm", "India Paytm payments & QR checkout", ("global",), "payment",
     [("Paytm for Business", "https://business.paytm.com/")], "paytm.com", "00BAF2", "Pt", "paytm"),
    ("cashfree", "Cashfree", "cashfree", "India Cashfree payment gateway", ("global",), "payment",
     [("Cashfree merchant", "https://www.cashfree.com/")], "cashfree.com", "00B386", "CF", None),
    ("ccavenue", "CCAvenue", "ccavenue", "India CCAvenue payment gateway", ("global",), "payment",
     [("CCAvenue merchant", "https://www.ccavenue.com/")], "ccavenue.com", "1A4788", "CC", None),
    ("instamojo", "Instamojo", "instamojo", "India Instamojo payments for SMBs", ("global",), "payment",
     [("Instamojo seller", "https://www.instamojo.com/")], "instamojo.com", "3DDC84", "IM", None),
    ("pine_labs", "Pine Labs", "pine_labs", "India Pine Labs POS & online acquiring", ("global",), "payment",
     [("Pine Labs merchant", "https://www.pinelabs.com/")], "pinelabs.com", "003DA5", "PL", None),
    ("payu_india", "PayU India", "payu", "India PayU payment gateway", ("global",), "payment",
     [("PayU India onboarding", "https://onboarding.payu.in/")], "payu.in", "A6C306", "PU", "payu"),
    ("bkash", "bKash", "bkash", "Bangladesh bKash mobile financial services", ("af",), "payment",
     [("bKash business", "https://www.bkash.com/business")], "bkash.com", "E2136E", "bK", None),
    ("khalti", "Khalti", "khalti", "Nepal Khalti digital wallet", ("sea",), "payment",
     [("Khalti merchant", "https://khalti.com/merchant")], "khalti.com", "5C2D91", "K", None),
    ("esewa", "eSewa", "esewa", "Nepal eSewa wallet checkout", ("sea",), "payment",
     [("eSewa merchant", "https://merchant.esewa.com.np/")], "esewa.com.np", "60BB46", "eS", None),
    ("lankaqr", "LankaQR", "lankaqr", "Sri Lanka LankaQR instant payments", ("sea",), "payment",
     [("LankaQR — LankaPay", "https://www.lankapay.net.lk/")], "lankapay.net.lk", "1B3281", "LQ", None),
    # AU / NZ
    ("poli", "POLi", "poli", "Australia / NZ POLi bank transfer checkout", ("au",), "payment",
     [("POLi Payments", "https://www.polipayments.com/")], "polipayments.com", "F58220", "PO", None),
    ("becs_direct_debit", "BECS Direct Debit", "becs", "Australia BECS bank debit via gateway", ("au",), "payment",
     [("Stripe BECS docs", "https://stripe.com/docs/payments/au-becs-debit")], "stripe.com", "635BFF", "BD", "stripe"),
    ("payto", "PayTo", "payto", "Australia PayTo real-time bank payments", ("au",), "payment",
     [("PayTo — AusPayNet", "https://www.auspayplus.com.au/payments/payto")], "auspayplus.com.au", "003DA5", "PT", None),
    ("windcave", "Windcave", "windcave", "New Zealand Windcave payment gateway", ("au",), "payment",
     [("Windcave merchant", "https://www.windcave.com/")], "windcave.com", "00A3E0", "WC", None),
    # Europe
    ("revolut", "Revolut Pay", "revolut", "Revolut Pay & Revolut Business checkout", ("eu", "uk"), "payment",
     [("Revolut Business", "https://business.revolut.com/"), ("Revolut Merchant API", "https://developer.revolut.com/")],
     "revolut.com", "191C1F", "R", "revolut"),
    ("ideal", "iDEAL", "ideal", "Netherlands iDEAL bank payments", ("eu",), "payment",
     [("iDEAL", "https://www.ideal.nl/en/")], "ideal.nl", "CC0066", "iD", "ideal"),
    ("bancontact", "Bancontact", "bancontact", "Belgium Bancontact card payments", ("eu",), "payment",
     [("Bancontact", "https://www.bancontact.com/en")], "bancontact.com", "005498", "BC", None),
    ("sofort", "Sofort", "sofort", "Germany / EU Sofort instant bank transfer", ("eu",), "payment",
     [("Sofort / Klarna", "https://www.klarna.com/international/merchant/")], "klarna.com", "FFB3C7", "SF", "klarna"),
    ("giropay", "giropay", "giropay", "Germany giropay online banking", ("eu",), "payment",
     [("giropay", "https://www.giropay.de/")], "giropay.de", "003087", "gp", None),
    ("eps", "EPS", "eps", "Austria EPS online banking", ("eu",), "payment",
     [("EPS", "https://www.eps-ueberweisung.at/")], "eps-ueberweisung.at", "C8102E", "EP", None),
    ("swish", "Swish", "swish", "Sweden Swish mobile payments", ("eu",), "payment",
     [("Swish for merchants", "https://www.swish.nu/")], "swish.nu", "FFFFFF", "Sw", None),
    ("vipps", "Vipps", "vipps", "Nordics Vipps / MobilePay wallet", ("eu",), "payment",
     [("Vipps MobilePay business", "https://vippsmobilepay.com/")], "vippsmobilepay.com", "FF5B24", "V", "vipps"),
    ("twint", "TWINT", "twint", "Switzerland TWINT mobile payments", ("eu",), "payment",
     [("TWINT business", "https://www.twint.ch/en/business/")], "twint.ch", "000000", "TW", None),
    ("bizum", "Bizum", "bizum", "Spain Bizum instant mobile payments", ("eu",), "payment",
     [("Bizum", "https://bizum.es/")], "bizum.es", "05C3DD", "Bz", None),
    ("satispay", "Satispay", "satispay", "Italy Satispay mobile wallet", ("eu",), "payment",
     [("Satispay Business", "https://www.satispay.com/en/business")], "satispay.com", "FF3B30", "Sa", "satispay"),
    ("payconiq", "Payconiq", "payconiq", "Belgium / Luxembourg Payconiq", ("eu",), "payment",
     [("Payconiq by Bancontact", "https://www.payconiq.com/")], "payconiq.com", "FF4785", "PQ", None),
    ("mb_way", "MB WAY", "mbway", "Portugal MB WAY mobile payments", ("eu",), "payment",
     [("MB WAY", "https://www.mbway.pt/")], "mbway.pt", "E60012", "MB", None),
    ("blik", "BLIK", "blik", "Poland BLIK mobile payments", ("eu",), "payment",
     [("BLIK", "https://www.blik.com/")], "blik.com", "000000", "BL", None),
    ("przelewy24", "Przelewy24", "p24", "Poland Przelewy24 online payments", ("eu",), "payment",
     [("Przelewy24 merchant", "https://www.przelewy24.pl/")], "przelewy24.pl", "D9272E", "P24", None),
    ("trustly", "Trustly", "trustly", "EU Trustly account-to-account payments", ("eu", "uk"), "payment",
     [("Trustly merchant", "https://www.trustly.net/")], "trustly.net", "0EE06E", "Tr", "trustly"),
    ("paysafe", "Paysafe", "paysafe", "Paysafe / Skrill / Neteller payments", ("eu", "uk"), "payment",
     [("Paysafe merchant", "https://www.paysafe.com/")], "paysafe.com", "008000", "PS", None),
    ("nuvei", "Nuvei", "nuvei", "Nuvei global payment platform", ("global", "eu", "uk"), "payment",
     [("Nuvei merchant", "https://www.nuvei.com/")], "nuvei.com", "00D4AA", "Nv", None),
    ("payu_europe", "PayU Europe", "payu", "PayU Europe payment gateway", ("eu",), "payment",
     [("PayU Europe", "https://corporate.payu.com/")], "payu.com", "A6C306", "PU", "payu"),
    ("worldline", "Worldline", "worldline", "Worldline / Ingenico acquiring", ("eu", "uk"), "payment",
     [("Worldline merchant", "https://worldline.com/")], "worldline.com", "0066CC", "WL", "worldline"),
    # Americas
    ("venmo", "Venmo", "venmo", "US Venmo business checkout (via PayPal/Braintree)", ("us",), "payment",
     [("Venmo business profiles", "https://venmo.com/business/profiles")], "venmo.com", "008CFF", "V", "venmo"),
    ("cash_app_pay", "Cash App Pay", "cashapp", "US Cash App Pay online checkout", ("us",), "payment",
     [("Cash App for Business", "https://cash.app/business")], "cash.app", "00D632", "Ca", "cashapp"),
    ("clover", "Clover", "clover", "US Clover POS & payments", ("us",), "payment",
     [("Clover merchant", "https://www.clover.com/")], "clover.com", "008060", "Cl", "clover"),
    ("toast", "Toast", "toast", "US Toast restaurant POS & payments", ("us",), "payment",
     [("Toast for restaurants", "https://pos.toasttab.com/")], "toasttab.com", "FF4C00", "To", None),
    ("lightspeed", "Lightspeed Payments", "lightspeed", "US / CA Lightspeed POS payments", ("us",), "payment",
     [("Lightspeed Payments", "https://www.lightspeedhq.com/payments/")], "lightspeedhq.com", "E31C3D", "LS", "lightspeed"),
    ("shopify_payments", "Shopify Payments", "shopify", "Shopify Payments for merchant stores", ("global",), "payment",
     [("Shopify Payments", "https://www.shopify.com/payments")], "shopify.com", "96BF48", "Sh", "shopify"),
    ("fiserv", "Fiserv", "fiserv", "US Fiserv / First Data merchant acquiring", ("us",), "payment",
     [("Fiserv merchant", "https://www.fiserv.com/")], "fiserv.com", "FF6600", "Fi", None),
    ("moneris", "Moneris", "moneris", "Canada Moneris payment processing", ("us",), "payment",
     [("Moneris merchant", "https://www.moneris.com/")], "moneris.com", "003DA5", "Mo", None),
    ("interac", "Interac Debit", "interac", "Canada Interac Debit — online & in-store via acquirer", ("ca",), "payment",
     [("Interac Debit for business", "https://www.interac.ca/en/business/products/interac-debit/"),
      ("Moneris Interac Online", "https://www.moneris.com/en/Products/Online/E-Commerce-Solutions/Interac-Online")],
     "interac.ca", "FFCC00", "Db", None),
    ("pagarme", "Pagar.me", "pagarme", "Brazil Pagar.me payment gateway", ("latam",), "payment",
     [("Pagar.me merchant", "https://pagar.me/")], "pagar.me", "65A300", "Pg", None),
    ("pagseguro", "PagSeguro", "pagseguro", "Brazil PagSeguro online payments", ("latam",), "payment",
     [("PagSeguro merchant", "https://pagseguro.uol.com.br/")], "pagseguro.uol.com.br", "FFC800", "PS", None),
    ("dlocal", "dLocal", "dlocal", "LATAM dLocal cross-border payments", ("latam",), "payment",
     [("dLocal merchant", "https://dlocal.com/")], "dlocal.com", "00B388", "dL", None),
    ("ebanx", "EBANX", "ebanx", "LATAM EBANX local payment methods", ("latam",), "payment",
     [("EBANX merchant", "https://www.ebanx.com/")], "ebanx.com", "0057FF", "EB", None),
    ("conekta", "Conekta", "conekta", "Mexico Conekta payment API", ("latam",), "payment",
     [("Conekta merchant", "https://www.conekta.com/")], "conekta.com", "000000", "Co", None),
    ("openpay", "OpenPay", "openpay", "Mexico OpenPay payment gateway", ("latam",), "payment",
     [("OpenPay merchant", "https://www.openpay.mx/")], "openpay.mx", "00A3E0", "OP", None),
    ("kushki", "Kushki", "kushki", "LATAM Kushki payment orchestration", ("latam",), "payment",
     [("Kushki merchant", "https://www.kushki.com/")], "kushki.com", "00B388", "Ku", None),
    ("payu_latam", "PayU Latam", "payu", "Latin America PayU gateway", ("latam",), "payment",
     [("PayU Latam", "https://latinamerica.payu.com/")], "payu.com", "A6C306", "PL", "payu"),
    # Africa / MENA
    ("chipper_cash", "Chipper Cash", "chipper", "Africa Chipper Cash business payments", ("af",), "payment",
     [("Chipper Cash business", "https://chippercash.com/business")], "chippercash.com", "6B46C1", "CC", None),
    ("mpesa", "M-Pesa", "mpesa", "East Africa M-Pesa mobile money", ("af",), "payment",
     [("M-Pesa for business", "https://www.safaricom.co.ke/business/m-pesa")], "safaricom.co.ke", "4CAF50", "MP", None),
    ("payfast", "PayFast", "payfast", "South Africa PayFast gateway", ("af",), "payment",
     [("PayFast merchant", "https://www.payfast.co.za/")], "payfast.co.za", "E60012", "PF", None),
    ("peach_payments", "Peach Payments", "peach", "South Africa Peach Payments", ("af",), "payment",
     [("Peach Payments", "https://peachpayments.com/")], "peachpayments.com", "FF6600", "Pe", None),
    ("hyperpay", "HyperPay", "hyperpay", "MENA HyperPay payment gateway", ("global",), "payment",
     [("HyperPay merchant", "https://www.hyperpay.com/")], "hyperpay.com", "003DA5", "HP", None),
    ("tap_payments", "Tap Payments", "tap", "MENA Tap Payments checkout", ("global",), "payment",
     [("Tap merchant", "https://www.tap.company/")], "tap.company", "0066FF", "Tp", None),
    ("paytabs", "PayTabs", "paytabs", "MENA PayTabs payment gateway", ("global",), "payment",
     [("PayTabs merchant", "https://site.paytabs.com/")], "paytabs.com", "003DA5", "PT", None),
    ("network_international", "Network International", "network", "MENA Network International acquiring", ("global",), "payment",
     [("Network merchant", "https://www.network.ae/")], "network.ae", "003DA5", "NI", None),
    ("fawry", "Fawry", "fawry", "Egypt Fawry bill & wallet payments", ("af",), "payment",
     [("Fawry business", "https://www.fawry.com/business")], "fawry.com", "0066CC", "Fw", None),
    # Global / cross-border
    ("wise", "Wise Business", "wise", "Wise Business cross-border collections", ("global", "eu", "uk"), "payment",
     [("Wise Business", "https://wise.com/business/")], "wise.com", "9FE870", "W", "wise"),
    ("payoneer", "Payoneer", "payoneer", "Payoneer global payout & collection", ("global",), "payment",
     [("Payoneer merchant", "https://www.payoneer.com/")], "payoneer.com", "FF4800", "Po", "payoneer"),
    ("bluesnap", "BlueSnap", "bluesnap", "BlueSnap global payment gateway", ("global",), "payment",
     [("BlueSnap merchant", "https://www.bluesnap.com/")], "bluesnap.com", "0066CC", "BS", None),
    ("paddle", "Paddle", "paddle", "Paddle SaaS billing & checkout", ("global",), "payment",
     [("Paddle merchant", "https://www.paddle.com/")], "paddle.com", "FDDD35", "Pd", "paddle"),
    ("fastspring", "FastSpring", "fastspring", "FastSpring SaaS commerce platform", ("global",), "payment",
     [("FastSpring merchant", "https://fastspring.com/")], "fastspring.com", "003DA5", "FS", None),
    ("twocheckout", "2Checkout", "2checkout", "2Checkout / Verifone global payments", ("global",), "payment",
     [("2Checkout merchant", "https://www.2checkout.com/")], "2checkout.com", "003DA5", "2C", "verifone"),
    ("cybersource", "CyberSource", "cybersource", "CyberSource enterprise payment gateway", ("global",), "payment",
     [("CyberSource merchant", "https://www.cybersource.com/")], "cybersource.com", "003DA5", "CS", None),
    ("global_payments", "Global Payments", "global_payments", "Global Payments enterprise acquiring", ("global",), "payment",
     [("Global Payments merchant", "https://www.globalpayments.com/")], "globalpayments.com", "003DA5", "GP", None),
    # BNPL
    ("sezzle", "Sezzle", "sezzle", "US Sezzle buy-now-pay-later", ("us",), "payment",
     [("Sezzle merchants", "https://sezzle.com/merchants")], "sezzle.com", "8333FF", "Sz", "sezzle"),
    ("splitit", "Splitit", "splitit", "Splitit instalment payments", ("global",), "payment",
     [("Splitit merchant", "https://www.splitit.com/")], "splitit.com", "003DA5", "Sp", None),
    ("tabby", "Tabby", "tabby", "MENA Tabby BNPL checkout", ("global",), "payment",
     [("Tabby business", "https://tabby.ai/business")], "tabby.ai", "3BFF9D", "Tb", None),
    ("tamara", "Tamara", "tamara", "MENA Tamara BNPL checkout", ("global",), "payment",
     [("Tamara business", "https://tamara.co/business")], "tamara.co", "000000", "Tm", None),
    ("hoolah", "Hoolah", "hoolah", "SG / MY Hoolah BNPL checkout", ("sea",), "payment",
     [("Hoolah merchants", "https://www.hoolah.co/merchants")], "hoolah.co", "FF4785", "Ho", None),
    ("grab_paylater", "Grab PayLater", "grab", "SEA Grab PayLater merchant checkout", ("sea",), "payment",
     [("Grab PayLater merchant", "https://www.grab.com/sg/finance/pay-later-merchant/")], "grab.com", "00B14F", "GP", "grab"),
    ("scalapay", "Scalapay", "scalapay", "EU Scalapay BNPL checkout", ("eu",), "payment",
     [("Scalapay merchants", "https://www.scalapay.com/merchants")], "scalapay.com", "F7CBCF", "Sc", None),
    ("clearpay", "Clearpay", "clearpay", "UK Clearpay BNPL (Afterpay brand)", ("uk",), "payment",
     [("Clearpay for retailers", "https://www.clearpay.co.uk/en-GB/for-retailers")], "clearpay.co.uk", "B2FCE4", "CP", "afterpay"),
    # Reputation — dining
    ("michelin_guide", "MICHELIN Guide", "michelin", "MICHELIN Guide restaurant listings & reviews", ("eu", "hk"), "reputation",
     [("MICHELIN Guide restaurant", "https://guide.michelin.com/"), ("TheFork MICHELIN partnership", "https://www.theforkmanager.com/en/restaurant-partnerships")],
     "guide.michelin.com", "BD2333", "M", None),
    ("zenchef", "Zenchef", "zenchef", "Europe Zenchef reservation CRM", ("eu",), "reputation",
     [("Zenchef for restaurants", "https://www.zenchef.com/")], "zenchef.com", "000000", "Z", None),
    ("sevenrooms", "SevenRooms", "sevenrooms", "SevenRooms guest CRM & reviews", ("us", "eu"), "reputation",
     [("SevenRooms", "https://sevenrooms.com/")], "sevenrooms.com", "091927", "7R", None),
    ("tock", "Tock", "tock", "US Tock prepaid reservations", ("us",), "reputation",
     [("Join Tock", "https://www.exploretock.com/join")], "exploretock.com", "000000", "Tk", None),
    ("covermanager", "CoverManager", "covermanager", "Spain / EU CoverManager reservations", ("eu",), "reputation",
     [("CoverManager", "https://covermanager.com/")], "covermanager.com", "FF5722", "CM", None),
    ("quandoo", "Quandoo", "quandoo", "Germany / EU Quandoo restaurant bookings", ("eu",), "reputation",
     [("Quandoo partners", "https://www.quandoo.com/partners")], "quandoo.com", "E23744", "Q", None),
    ("eat_app", "Eat App", "eat_app", "Eat App reservations & guest data", ("global", "sea"), "reputation",
     [("Eat App", "https://eat.app/")], "eat.app", "FF5722", "EA", None),
    ("dish", "DISH", "dish", "DISH restaurant website & guest engagement", ("us",), "reputation",
     [("DISH", "https://get.dish.co/")], "dish.co", "FF5722", "Di", None),
    ("bentobox", "BentoBox", "bentobox", "BentoBox restaurant websites & reviews", ("us",), "reputation",
     [("BentoBox", "https://getbento.com/")], "getbento.com", "000000", "BB", None),
    ("doordash", "DoorDash", "doordash", "US / CA / AU DoorDash restaurant reviews", ("us", "au"), "reputation",
     [("DoorDash for Merchants", "https://get.doordash.com/")], "doordash.com", "FF3008", "DD", "doordash"),
    ("just_eat", "Just Eat", "just_eat", "UK / EU Just Eat Takeaway restaurant platform", ("eu", "uk"), "reputation",
     [("Just Eat Partner", "https://partner.just-eat.co.uk/")], "just-eat.co.uk", "FF8000", "JE", "justeat"),
    ("swiggy", "Swiggy", "swiggy", "India Swiggy restaurant partner reviews", ("global",), "reputation",
     [("Swiggy Partner", "https://partner.swiggy.com/")], "swiggy.com", "FC8019", "Sw", None),
    ("glovo", "Glovo", "glovo", "EU / LATAM Glovo delivery partner", ("eu", "latam"), "reputation",
     [("Glovo Partners", "https://glovoapp.com/en/partners/")], "glovoapp.com", "FFC244", "Gl", "glovo"),
    ("wolt", "Wolt", "wolt", "Europe Wolt merchant reviews", ("eu",), "reputation",
     [("Wolt Partner", "https://explore.wolt.com/en/partner")], "wolt.com", "009DE0", "Wo", "wolt"),
    ("bolt_food", "Bolt Food", "bolt", "EU Bolt Food restaurant partner", ("eu",), "reputation",
     [("Bolt Food partner", "https://bolt.eu/en/food/partner/")], "bolt.eu", "34D186", "BF", "bolt"),
    ("rappi", "Rappi", "rappi", "LATAM Rappi restaurant partner", ("latam",), "reputation",
     [("Rappi restaurants", "https://www.rappi.com/restaurants")], "rappi.com", "FF441F", "Ra", "rappi"),
    ("ifood", "iFood", "ifood", "Brazil iFood restaurant partner", ("latam",), "reputation",
     [("iFood Restaurante", "https://restaurante.ifood.com.br/")], "ifood.com.br", "EA1D2C", "iF", "ifood"),
    ("menulog", "Menulog", "menulog", "Australia Menulog restaurant partner", ("au",), "reputation",
     [("Menulog Partner", "https://partner.menulog.com.au/")], "menulog.com.au", "FF8000", "ML", None),
    ("skipthedishes", "SkipTheDishes", "skip", "Canada Skip restaurant partner", ("us",), "reputation",
     [("Skip for Restaurants", "https://restaurants.skipthedishes.com/")], "skipthedishes.com", "E80020", "Sk", None),
    # Travel / OTA
    ("hotels_com", "Hotels.com", "hotels", "Hotels.com partner reviews (Expedia Group)", ("global",), "reputation",
     [("Expedia Partner Central", "https://www.expediapartnercentral.com/")], "hotels.com", "D32F2F", "H", "hotelsdotcom"),
    ("vrbo", "Vrbo", "vrbo", "Vrbo vacation rental owner reviews", ("global",), "reputation",
     [("List on Vrbo", "https://www.vrbo.com/join")], "vrbo.com", "006ED1", "V", None),
    ("hostelworld", "Hostelworld", "hostelworld", "Hostelworld property reviews", ("global",), "reputation",
     [("Hostelworld Inbox", "https://inbox.hostelworld.com/")], "hostelworld.com", "F25623", "HW", None),
    ("airbnb", "Airbnb", "airbnb", "Airbnb host reviews & listings", ("global",), "reputation",
     [("Airbnb hosting", "https://www.airbnb.com/host/homes")], "airbnb.com", "FF5A5F", "Ab", "airbnb"),
    ("trivago", "Trivago", "trivago", "Trivago hotel meta-search reviews", ("global", "eu"), "reputation",
     [("Trivago advertisers", "https://advertisers.trivago.com/")], "trivago.com", "007FAD", "Tr", "trivago"),
    ("kayak", "Kayak", "kayak", "Kayak business travel listings", ("global",), "reputation",
     [("Kayak for Business", "https://www.kayak.com/business")], "kayak.com", "FF690F", "Ky", "kayak"),
    ("skyscanner", "Skyscanner", "skyscanner", "Skyscanner partner travel listings", ("global",), "reputation",
     [("Skyscanner Partners", "https://partners.skyscanner.net/")], "skyscanner.net", "0770E3", "SS", "skyscanner"),
    ("makemytrip", "MakeMyTrip", "makemytrip", "India MakeMyTrip hotel partner reviews", ("global",), "reputation",
     [("MakeMyTrip hotel partnership", "https://www.makemytrip.com/hotels/hotel-partnership.php")], "makemytrip.com", "008CFF", "MM", None),
    ("cleartrip", "Cleartrip", "cleartrip", "India / MENA Cleartrip partner reviews", ("global",), "reputation",
     [("Cleartrip partners", "https://www.cleartrip.com/partners")], "cleartrip.com", "F16022", "CT", None),
    ("traveloka", "Traveloka", "traveloka", "SEA Traveloka partner reviews", ("sea",), "reputation",
     [("Traveloka partnership", "https://www.traveloka.com/en-id/partnership")], "traveloka.com", "0194F3", "TV", "traveloka"),
    ("reddoorz", "RedDoorz", "reddoorz", "SEA RedDoorz property partner", ("sea",), "reputation",
     [("RedDoorz partnership", "https://partnership.reddoorz.com/")], "reddoorz.com", "E60012", "RD", None),
    # Social / messaging
    ("instagram_business", "Instagram Business", "instagram", "Instagram business profile & social proof", ("global",), "reputation",
     [("Instagram for Business", "https://business.instagram.com/")], "instagram.com", "E4405F", "Ig", "instagram"),
    ("tiktok_business", "TikTok for Business", "tiktok", "TikTok business account & reviews", ("global",), "reputation",
     [("TikTok for Business", "https://www.tiktok.com/business/")], "tiktok.com", "000000", "Tk", "tiktok"),
    ("linkedin_company", "LinkedIn Company", "linkedin", "LinkedIn company page & B2B reputation", ("global",), "reputation",
     [("Create LinkedIn Page", "https://www.linkedin.com/company/setup/new/")], "linkedin.com", "0A66C2", "Li", "linkedin"),
    ("youtube_brand", "YouTube Brand", "youtube", "YouTube brand channel & video reviews", ("global",), "reputation",
     [("YouTube account", "https://www.youtube.com/account")], "youtube.com", "FF0000", "Yt", "youtube"),
    ("whatsapp_business", "WhatsApp Business", "whatsapp", "WhatsApp Business customer messaging", ("global",), "reputation",
     [("WhatsApp Business", "https://business.whatsapp.com/")], "whatsapp.com", "25D366", "Wa", "whatsapp"),
    ("line_official", "LINE Official Account", "line", "LINE Official Account — JP / TW / TH", ("jp", "tw", "sea"), "reputation",
     [("LINE Biz", "https://www.linebiz.com/")], "line.me", "00C300", "LN", "line"),
    # APAC dining
    ("eatigo", "Eatigo", "eatigo", "TH / SG / MY Eatigo restaurant partner", ("sea",), "reputation",
     [("Eatigo restaurant", "https://restaurant.eatigo.com/")], "eatigo.com", "FF5722", "Eg", None),
    ("funnow", "FunNow", "funnow", "TW / HK / JP FunNow instant booking", ("tw", "hk", "jp"), "reputation",
     [("FunNow merchant", "https://merchant.funnow.com.tw/")], "funnow.com", "FFB800", "FN", None),
    ("inline", "inline", "inline", "Taiwan inline table booking & CRM", ("tw",), "reputation",
     [("inline merchant", "https://inline.app/")], "inline.app", "FF5722", "in", None),
    ("ichef", "iCHEF", "ichef", "Taiwan iCHEF POS & guest CRM", ("tw",), "reputation",
     [("iCHEF", "https://www.ichefpos.com/")], "ichefpos.com", "FF5722", "iC", None),
    ("retty", "Retty", "retty", "Japan Retty restaurant reviews", ("jp",), "reputation",
     [("Retty owner", "https://owner.retty.me/")], "retty.me", "FF5722", "Re", None),
    ("naver_place", "Naver Place", "naver", "Korea Naver Place business reviews", ("kr",), "reputation",
     [("Naver Smart Place", "https://new.smartplace.naver.com/")], "naver.com", "03C75A", "NP", "naver"),
    ("kakao_map", "Kakao Map", "kakao", "Korea Kakao Map business reviews", ("kr",), "reputation",
     [("Kakao Map merchant", "https://map.kakao.com/")], "kakao.com", "FFCD00", "KM", "kakao"),
    # E-commerce / marketplaces
    ("shopee_seller", "Shopee Seller", "shopee", "Shopee seller shop ratings", ("sea",), "reputation",
     [("Shopee Seller Centre", "https://seller.shopee.com/")], "shopee.com", "EE4D2D", "SS", "shopee"),
    ("lazada_seller", "Lazada Seller", "lazada", "Lazada seller store ratings", ("sea",), "reputation",
     [("Lazada Seller", "https://sell.lazada.com/")], "lazada.com", "0F146D", "Lz", "lazada"),
    ("amazon_seller", "Amazon Seller", "amazon", "Amazon Seller Central ratings", ("global",), "reputation",
     [("Amazon Seller Central", "https://sellercentral.amazon.com/")], "amazon.com", "FF9900", "Am", "amazon"),
    ("ebay_seller", "eBay Seller", "ebay", "eBay seller feedback scores", ("global",), "reputation",
     [("eBay Seller Hub", "https://www.ebay.com/sh/landing")], "ebay.com", "E53238", "eB", "ebay"),
    ("etsy_shop", "Etsy Shop", "etsy", "Etsy shop reviews", ("global",), "reputation",
     [("Sell on Etsy", "https://www.etsy.com/sell")], "etsy.com", "F45800", "Et", "etsy"),
    ("shopify", "Shopify", "shopify", "Shopify store reviews & apps", ("global",), "reputation",
     [("Shopify", "https://www.shopify.com/")], "shopify.com", "96BF48", "Sh", "shopify"),
    ("woocommerce", "WooCommerce", "woocommerce", "WooCommerce store reviews plugin", ("global",), "reputation",
     [("WooCommerce", "https://woocommerce.com/")], "woocommerce.com", "96588A", "Wc", "woocommerce"),
    ("bigcommerce", "BigCommerce", "bigcommerce", "BigCommerce store reviews", ("global",), "reputation",
     [("BigCommerce", "https://www.bigcommerce.com/")], "bigcommerce.com", "121118", "BC", "bigcommerce"),
    ("magento", "Magento", "magento", "Adobe Commerce / Magento store reviews", ("global",), "reputation",
     [("Adobe Commerce", "https://business.adobe.com/products/magento/magento-commerce.html")], "adobe.com", "FF0000", "Mg", "adobe"),
    ("tiktok_shop", "TikTok Shop", "tiktok", "TikTok Shop seller ratings", ("global", "sea"), "reputation",
     [("TikTok Shop Seller", "https://seller.tiktok.com/")], "tiktok.com", "000000", "TS", "tiktok"),
    ("tokopedia", "Tokopedia", "tokopedia", "Indonesia Tokopedia seller ratings", ("sea",), "reputation",
     [("Tokopedia Seller", "https://seller.tokopedia.com/")], "tokopedia.com", "42B549", "Tp", None),
    ("bukalapak", "Bukalapak", "bukalapak", "Indonesia Bukalapak seller ratings", ("sea",), "reputation",
     [("Bukalapak partnership", "https://www.bukalapak.com/l/partnership")], "bukalapak.com", "E31C23", "Bk", None),
    ("qoo10", "Qoo10", "qoo10", "JP / SG Qoo10 seller ratings", ("jp", "sea"), "reputation",
     [("Qoo10 Seller", "https://www.qoo10.sg/gmkt.inc/Seller/")], "qoo10.sg", "E60012", "Q10", None),
    ("rakuten_ichiba", "Rakuten Ichiba", "rakuten", "Japan Rakuten marketplace shop ratings", ("jp",), "reputation",
     [("Rakuten RMS", "https://www.rms.rakuten.co.jp/")], "rakuten.co.jp", "BF0000", "Ri", "rakuten"),
    ("yahoo_shopping_jp", "Yahoo! Shopping JP", "yahoo", "Japan Yahoo! Shopping store ratings", ("jp",), "reputation",
     [("Yahoo! Store", "https://pro.store.yahoo.co.jp/")], "yahoo.co.jp", "6001D2", "Y!", None),
]

SIMPLE_ICONS = {s[0]: s[10] for s in SPECS if s[10]}


def _steps_payment(name: str) -> list[str]:
    return [
        f"Open the official {name} merchant portal (link below) and apply as a business owner — not a personal account.",
        "Complete KYC / business verification required for live checkout.",
        "In the merchant or developer console, create API credentials with payment-only scopes.",
        "Copy Merchant ID, API Key, and API Secret (names may differ by provider).",
        *SECURITY_STEPS,
        "Paste credentials below → Save & verify. Checkout charges your merchant account.",
    ]


def _steps_reputation(name: str) -> list[str]:
    return [
        f"Claim or register your business on {name} using the owner portal below.",
        "Verify ownership (phone, email, or documents) as the official business representative.",
        "After access, open your listing and copy the Business / listing ID from the URL or settings.",
        *SECURITY_STEPS,
        "Paste Business ID below. Add an API key only if the platform issued partner API access. Save & verify.",
    ]


def _payment_plugin(spec: tuple) -> str:
    slug, name, provider, desc, regions, _, links, *_ = spec
    link_lines = ",\n".join(
        f'                {{"label": "{lbl}", "url": "{url}"}}' for lbl, url in links
    )
    region_str = ", ".join(f'"{r}"' for r in regions)
    return f"""    {{
        "slug": "{slug}",
        "name": "{name}",
        "provider": "{provider}",
        "description": "{desc}",
        "regions": ({region_str},),
        "checkout_ready": True,
        "credential_fields": _CRED_MERCHANT,
        "setup_guide": {{
            "summary": "Apply as a {name} merchant, then paste Merchant ID + API keys from the owner console.",
            "steps": {repr(_steps_payment(name))},
            "links": [
{link_lines}
            ],
        }},
    }}"""


def _reputation_plugin(spec: tuple) -> str:
    slug, name, provider, desc, regions, _, links, *_ = spec
    link_lines = ",\n".join(
        f'                {{"label": "{lbl}", "url": "{url}"}}' for lbl, url in links
    )
    region_str = ", ".join(f'"{r}"' for r in regions)
    caps = ("read_reviews", "read_rating")
    if "reservation" in desc.lower() or slug in {
        "zenchef", "sevenrooms", "tock", "covermanager", "quandoo", "eat_app",
        "inline", "funnow", "eatigo",
    }:
        caps = ("read_reviews", "read_rating", "reservation_feedback")
    cap_str = ", ".join(f'"{c}"' for c in caps)
    return f"""    {{
        "slug": "{slug}",
        "name": "{name}",
        "provider": "{provider}",
        "description": "{desc}",
        "regions": ({region_str},),
        "capabilities": ({cap_str},),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {{
            "summary": "Claim your listing on {name}, then paste the business / listing ID from the owner console.",
            "steps": {repr(_steps_reputation(name))},
            "links": [
{link_lines}
            ],
        }},
    }}"""


def main() -> None:
    payments = [_payment_plugin(s) for s in SPECS if s[5] == "payment"]
    reps = [_reputation_plugin(s) for s in SPECS if s[5] == "reputation"]

    brands = []
    colors = []
    initials = []
    for slug, name, provider, desc, regions, cat, links, domain, color, initial, si in SPECS:
        brands.append(f'    "{slug}": {{"domain": "{domain}"}},')
        colors.append(f'    "{slug}": "{color}",')
        initials.append(f'    "{slug}": "{initial}",')

    si_lines = [f'    "{k}": "{v}",' for k, v in sorted(SIMPLE_ICONS.items())]

    pay_block = ",\n".join(payments)
    rep_block = ",\n".join(reps)
    brands_block = "\n".join(brands)
    colors_block = "\n".join(colors)
    initials_block = "\n".join(initials)
    si_block = "\n".join(si_lines)

    body = '''"""Batch-2 integration catalog plugins — generated by scripts/build_batch2_catalog.py."""

from __future__ import annotations

from typing import Any

# Re-use credential templates from main catalog at merge time.
_CRED_MERCHANT = [
    {"key": "merchant_id", "label": "Merchant ID", "required": True},
    {"key": "api_key", "label": "API Key", "required": True},
    {"key": "api_secret", "label": "API Secret", "type": "password", "required": True},
]
_CRED_REVIEW = [
    {"key": "business_id", "label": "Business / listing ID", "required": True},
    {"key": "api_key", "label": "API Key (if required)", "type": "password"},
]

EXTRA_PAYMENT_PLUGINS: tuple[dict[str, Any], ...] = (
''' + pay_block + ''',
)

EXTRA_REPUTATION_PLUGINS: tuple[dict[str, Any], ...] = (
''' + rep_block + ''',
)

EXTRA_PLUGIN_BRANDS: dict[str, dict[str, str]] = {
''' + brands_block + '''
}

EXTRA_BRAND_COLORS: dict[str, str] = {
''' + colors_block + '''
}

EXTRA_BRAND_INITIALS: dict[str, str] = {
''' + initials_block + '''
}

BATCH2_SIMPLE_ICONS: dict[str, str] = {
''' + si_block + '''
}
'''
    OUT.write_text(body, encoding="utf-8")
    print(f"Wrote {OUT} — {len(payments)} payment + {len(reps)} reputation plugins")


if __name__ == "__main__":
    main()
