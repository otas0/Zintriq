"""Mainland China payment & review plugins + a few global coverage gaps."""

from __future__ import annotations

from typing import Any

_CRED_MERCHANT = [
    {"key": "merchant_id", "label": "Merchant ID", "required": True},
    {"key": "api_key", "label": "API Key", "required": True},
    {"key": "api_secret", "label": "API Secret", "type": "password", "required": True},
]

_CRED_REVIEW = [
    {"key": "business_id", "label": "Business / listing ID", "required": True},
    {"key": "api_key", "label": "API key (optional)", "type": "password", "required": False},
]

_SECURITY = [
    "Store API keys only in this encrypted vault — never in email, chat, or public repos.",
    "Use sandbox / test keys first; switch to live keys only after owner verification is complete.",
    "Restrict API keys to the minimum scopes (payments or read-reviews only).",
    "Rotate keys if a staff member with access leaves the business.",
]


def _pay(name: str) -> list[str]:
    return [
        f"Open the official {name} merchant portal (link below) and apply as a business owner — not a personal account.",
        "Complete KYC / business verification required for live checkout.",
        "In the merchant or developer console, create API credentials with payment-only scopes.",
        "Copy Merchant ID, API Key, and API Secret (field names may differ by provider).",
        *_SECURITY,
        "Paste credentials below → Save & verify. Checkout charges your merchant account.",
    ]


def _rev(name: str) -> list[str]:
    return [
        f"Claim or register your business on {name} using the owner portal below.",
        "Verify ownership (phone, email, or documents) as the official business representative.",
        "After access, open your listing and copy the Business / listing ID from the URL or settings.",
        *_SECURITY,
        "Paste Business ID below. Add an API key only if the platform issued partner API access. Save & verify.",
    ]


def _pay_plugin(
    slug: str,
    name: str,
    provider: str,
    description: str,
    regions: tuple[str, ...],
    links: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "slug": slug,
        "name": name,
        "provider": provider,
        "description": description,
        "regions": regions,
        "checkout_ready": True,
        "credential_fields": _CRED_MERCHANT,
        "setup_guide": {
            "summary": f"Apply as a merchant on {name}, then paste API credentials from the owner console.",
            "steps": _pay(name),
            "links": links,
        },
    }


def _rev_plugin(
    slug: str,
    name: str,
    provider: str,
    description: str,
    regions: tuple[str, ...],
    links: list[dict[str, str]],
    capabilities: tuple[str, ...] = ("read_reviews", "read_rating"),
) -> dict[str, Any]:
    return {
        "slug": slug,
        "name": name,
        "provider": provider,
        "description": description,
        "regions": regions,
        "capabilities": capabilities,
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": f"Claim your listing on {name}, then paste the business / listing ID from the owner console.",
            "steps": _rev(name),
            "links": links,
        },
    }


CN = ("cn",)
CN_HK = ("cn", "hk")
CN_GLOBAL = ("cn", "global", "hk", "tw", "mo", "sea")

EXTRA_PAYMENT_PLUGINS: tuple[dict[str, Any], ...] = (
    _pay_plugin(
        "alipay",
        "Alipay",
        "alipay",
        "Mainland China Alipay (支付宝) online & in-store checkout",
        CN_GLOBAL,
        [
            {"label": "Alipay Open Platform", "url": "https://open.alipay.com/"},
            {"label": "Alipay merchant services", "url": "https://b.alipay.com/"},
        ],
    ),
    _pay_plugin(
        "wechat_pay",
        "WeChat Pay",
        "wechat_pay",
        "Mainland China WeChat Pay (微信支付)",
        CN_GLOBAL,
        [
            {"label": "WeChat Pay merchant", "url": "https://pay.weixin.qq.com/"},
            {"label": "WeChat Pay Open Platform", "url": "https://pay.weixin.qq.com/index.php/core/home/login"},
        ],
    ),
    _pay_plugin(
        "yunshanfu",
        "Yunshanfu / UnionPay QR",
        "unionpay",
        "China UnionPay Cloud QuickPass (云闪付) QR payments",
        CN,
        [
            {"label": "UnionPay merchant", "url": "https://merchant.unionpay.com/"},
            {"label": "Cloud QuickPass", "url": "https://www.unionpayintl.com/"},
        ],
    ),
    _pay_plugin(
        "jd_pay",
        "JD Pay",
        "jd",
        "JD.com / Jingdong Pay (京东支付)",
        CN,
        [{"label": "JD Pay merchant", "url": "https://pay.jd.com/"}],
    ),
    _pay_plugin(
        "douyin_pay",
        "Douyin Pay",
        "bytedance",
        "Douyin / ByteDance merchant payments (抖音支付)",
        CN,
        [{"label": "Douyin Open Platform", "url": "https://developer.open-douyin.com/"}],
    ),
    _pay_plugin(
        "meituan_pay",
        "Meituan Pay",
        "meituan",
        "Meituan merchant payments (美团支付)",
        CN,
        [{"label": "Meituan for merchants", "url": "https://e.meituan.com/"}],
    ),
    _pay_plugin(
        "bestpay",
        "BestPay",
        "bestpay",
        "China Telecom BestPay (翼支付)",
        CN,
        [{"label": "BestPay merchant", "url": "https://www.bestpay.com.cn/"}],
    ),
    _pay_plugin(
        "chinaums",
        "China UMS",
        "chinaums",
        "China UnionPay Merchant Services (银联商务)",
        CN,
        [{"label": "China UMS", "url": "https://www.chinaums.com/"}],
    ),
    _pay_plugin(
        "allinpay",
        "Allinpay",
        "allinpay",
        "Allinpay (通联支付) — China acquiring & wallets",
        CN,
        [{"label": "Allinpay", "url": "https://www.allinpay.com/"}],
    ),
    _pay_plugin(
        "lakala",
        "Lakala",
        "lakala",
        "Lakala (拉卡拉) China payment acceptance",
        CN,
        [{"label": "Lakala merchant", "url": "https://www.lakala.com/"}],
    ),
    _pay_plugin(
        "yeepay",
        "Yeepay",
        "yeepay",
        "Yeepay (易宝支付) China online payments",
        CN,
        [{"label": "Yeepay", "url": "https://www.yeepay.com/"}],
    ),
    _pay_plugin(
        "pingpp",
        "Ping++",
        "pingpp",
        "Ping++ payment orchestration for China wallets",
        CN,
        [{"label": "Ping++", "url": "https://www.pingxx.com/"}],
    ),
    # Global coverage gaps
    _pay_plugin(
        "pix",
        "Pix",
        "pix",
        "Brazil Pix instant payments",
        ("latam", "global"),
        [{"label": "Banco Central — Pix", "url": "https://www.bcb.gov.br/estabilidadefinanceira/pix"}],
    ),
    _pay_plugin(
        "mobilepay",
        "MobilePay",
        "mobilepay",
        "Nordic MobilePay wallet (Denmark / Finland)",
        ("eu",),
        [{"label": "MobilePay for business", "url": "https://www.mobilepay.fi/"}],
    ),
    _pay_plugin(
        "multibanco",
        "Multibanco",
        "multibanco",
        "Portugal Multibanco / SIBS reference payments",
        ("eu",),
        [{"label": "SIBS Multibanco", "url": "https://www.sibs.pt/"}],
    ),
    _pay_plugin(
        "antom",
        "Antom",
        "antom",
        "Ant International Antom — global acquiring for Alipay+ wallets",
        ("global", "cn", "hk", "sea", "eu", "uk", "us", "au"),
        [{"label": "Antom", "url": "https://www.antom.com/"}],
    ),
)

EXTRA_REPUTATION_PLUGINS: tuple[dict[str, Any], ...] = (
    _rev_plugin(
        "dianping",
        "Dianping",
        "dianping",
        "大众点评 — mainland China local reviews",
        CN,
        [{"label": "Dianping for merchants", "url": "https://e.dianping.com/"}],
    ),
    _rev_plugin(
        "meituan",
        "Meituan",
        "meituan",
        "美团商家 — orders, ratings & reviews",
        CN,
        [{"label": "Meituan merchant", "url": "https://e.meituan.com/"}],
        ("read_reviews", "read_rating", "orders"),
    ),
    _rev_plugin(
        "xiaohongshu",
        "Xiaohongshu",
        "xiaohongshu",
        "小红书 (RED) — brand & store reviews",
        CN,
        [{"label": "Xiaohongshu creator / brand", "url": "https://www.xiaohongshu.com/"}],
    ),
    _rev_plugin(
        "douyin",
        "Douyin",
        "bytedance",
        "抖音来客 — short-video storefront reviews",
        CN,
        [{"label": "Douyin Open Platform", "url": "https://developer.open-douyin.com/"}],
    ),
    _rev_plugin(
        "weibo",
        "Weibo",
        "weibo",
        "微博 — social reputation & brand mentions",
        CN,
        [{"label": "Weibo Open Platform", "url": "https://open.weibo.com/"}],
    ),
    _rev_plugin(
        "baidu_maps",
        "Baidu Maps",
        "baidu",
        "百度地图商家 — local listing & ratings",
        CN,
        [{"label": "Baidu Maps merchant", "url": "https://map.baidu.com/"}],
    ),
    _rev_plugin(
        "amap",
        "Amap / Gaode",
        "amap",
        "高德地图商家 — local listing & ratings",
        CN,
        [{"label": "Amap merchant", "url": "https://lbs.amap.com/"}],
    ),
    _rev_plugin(
        "eleme",
        "Ele.me",
        "eleme",
        "饿了么 — food delivery merchant ratings",
        CN,
        [{"label": "Ele.me merchant", "url": "https://open.shop.ele.me/"}],
        ("read_reviews", "read_rating", "orders"),
    ),
    _rev_plugin(
        "kuaishou",
        "Kuaishou",
        "kuaishou",
        "快手商家 — short-video storefront reviews",
        CN,
        [{"label": "Kuaishou Open Platform", "url": "https://open.kuaishou.com/"}],
    ),
    _rev_plugin(
        "taobao_seller",
        "Taobao Seller",
        "taobao",
        "淘宝卖家 — store ratings & reviews",
        CN,
        [{"label": "Taobao Open Platform", "url": "https://open.taobao.com/"}],
        ("read_reviews", "read_rating", "orders"),
    ),
    _rev_plugin(
        "tmall_seller",
        "Tmall Seller",
        "tmall",
        "天猫商家 — brand store ratings",
        CN,
        [{"label": "Tmall merchant", "url": "https://www.tmall.com/"}],
        ("read_reviews", "read_rating", "orders"),
    ),
    _rev_plugin(
        "jd_seller",
        "JD Seller",
        "jd",
        "京东商家 — marketplace ratings & reviews",
        CN,
        [{"label": "JD Open Platform", "url": "https://open.jd.com/"}],
        ("read_reviews", "read_rating", "orders"),
    ),
    _rev_plugin(
        "pinduoduo_seller",
        "Pinduoduo Seller",
        "pinduoduo",
        "拼多多商家 — marketplace ratings",
        CN,
        [{"label": "Pinduoduo Open Platform", "url": "https://open.pinduoduo.com/"}],
        ("read_reviews", "read_rating", "orders"),
    ),
)

EXTRA_PLUGIN_BRANDS: dict[str, dict[str, str]] = {
    "alipay": {"domain": "alipay.com"},
    "wechat_pay": {"domain": "pay.weixin.qq.com"},
    "yunshanfu": {"domain": "unionpay.com"},
    "jd_pay": {"domain": "jd.com"},
    "douyin_pay": {"domain": "douyin.com"},
    "meituan_pay": {"domain": "meituan.com"},
    "bestpay": {"domain": "bestpay.com.cn"},
    "chinaums": {"domain": "chinaums.com"},
    "allinpay": {"domain": "allinpay.com"},
    "lakala": {"domain": "lakala.com"},
    "yeepay": {"domain": "yeepay.com"},
    "pingpp": {"domain": "pingxx.com"},
    "pix": {"domain": "bcb.gov.br"},
    "mobilepay": {"domain": "mobilepay.fi"},
    "multibanco": {"domain": "sibs.pt"},
    "antom": {"domain": "antom.com"},
    "dianping": {"domain": "dianping.com"},
    "meituan": {"domain": "meituan.com"},
    "xiaohongshu": {"domain": "xiaohongshu.com"},
    "douyin": {"domain": "douyin.com"},
    "weibo": {"domain": "weibo.com"},
    "baidu_maps": {"domain": "map.baidu.com"},
    "amap": {"domain": "amap.com"},
    "eleme": {"domain": "ele.me"},
    "kuaishou": {"domain": "kuaishou.com"},
    "taobao_seller": {"domain": "taobao.com"},
    "tmall_seller": {"domain": "tmall.com"},
    "jd_seller": {"domain": "jd.com"},
    "pinduoduo_seller": {"domain": "pinduoduo.com"},
}

EXTRA_BRAND_COLORS: dict[str, str] = {
    "alipay": "1677FF",
    "wechat_pay": "07C160",
    "yunshanfu": "E21836",
    "jd_pay": "E1251B",
    "douyin_pay": "000000",
    "meituan_pay": "FFD100",
    "bestpay": "E60012",
    "chinaums": "003DA5",
    "allinpay": "004B9B",
    "lakala": "E60012",
    "yeepay": "00A0E9",
    "pingpp": "2D8CFF",
    "pix": "32BCAD",
    "mobilepay": "5A78FF",
    "multibanco": "003399",
    "antom": "1677FF",
    "dianping": "FF6633",
    "meituan": "FFD100",
    "xiaohongshu": "FF2442",
    "douyin": "000000",
    "weibo": "E6162D",
    "baidu_maps": "2932E1",
    "amap": "0091FF",
    "eleme": "0097FF",
    "kuaishou": "FF4906",
    "taobao_seller": "FF5000",
    "tmall_seller": "FF0036",
    "jd_seller": "E1251B",
    "pinduoduo_seller": "E02E24",
}

EXTRA_BRAND_INITIALS: dict[str, str] = {
    "alipay": "支",
    "wechat_pay": "微",
    "yunshanfu": "云",
    "jd_pay": "JD",
    "douyin_pay": "抖",
    "meituan_pay": "美",
    "bestpay": "翼",
    "chinaums": "UM",
    "allinpay": "通",
    "lakala": "拉",
    "yeepay": "易",
    "pingpp": "P+",
    "pix": "Px",
    "mobilepay": "MP",
    "multibanco": "MB",
    "antom": "An",
    "dianping": "点",
    "meituan": "美",
    "xiaohongshu": "红",
    "douyin": "抖",
    "weibo": "微",
    "baidu_maps": "百",
    "amap": "高",
    "eleme": "饿",
    "kuaishou": "快",
    "taobao_seller": "淘",
    "tmall_seller": "猫",
    "jd_seller": "京",
    "pinduoduo_seller": "拼",
}
