"""Fictional demo products; these are not live listings or real stock."""

from app.domain.catalog import Money, Product, Sku


def demo_catalog() -> tuple[Product, ...]:
    return (
        Product(id="demo-headphones-01", name="静听 Pro 降噪耳机", brand="Buyvora Lab",
                category="headphones", description="头戴式蓝牙降噪耳机，适合通勤和学习。",
                tags=("耳机", "降噪", "蓝牙", "headphones", "audio"),
                skus=(Sku(id="hp01-black", name="黑色", price=Money(amount_minor=29900), stock=8),
                      Sku(id="hp01-white", name="白色", price=Money(amount_minor=31900), stock=0))),
        Product(id="demo-headphones-02", name="轻听 Air 无线耳机", brand="Buyvora Lab",
                category="headphones", description="轻便入耳式蓝牙耳机，适合日常通话。",
                tags=("耳机", "蓝牙", "headphones", "audio"),
                skus=(Sku(id="hp02-white", name="白色", price=Money(amount_minor=15990), stock=12),)),
        Product(id="demo-keyboard-01", name="方格 K75 机械键盘", brand="Keycraft",
                category="keyboards", description="75% 配列机械键盘，支持有线连接。",
                tags=("键盘", "机械", "keyboard"),
                skus=(Sku(id="kb01-red", name="红轴", price=Money(amount_minor=24900), stock=6),
                      Sku(id="kb01-brown", name="茶轴", price=Money(amount_minor=26900), stock=4))),
        Product(id="demo-mouse-01", name="轻点 M1 无线鼠标", brand="Keycraft",
                category="mice", description="轻量无线鼠标，适合移动办公。",
                tags=("鼠标", "无线", "mouse"),
                skus=(Sku(id="ms01-grey", name="灰色", price=Money(amount_minor=8990), stock=20),)),
        Product(id="demo-hub-01", name="拓展 H6 USB-C 扩展坞", brand="Linkway",
                category="hubs", description="六接口扩展坞，包含 HDMI 和 USB-A 接口。",
                tags=("扩展坞", "转接器", "hub", "usb-c"),
                skus=(Sku(id="hub01-silver", name="银色", price=Money(amount_minor=18900), stock=0),)),
        Product(id="demo-monitor-01", name="清晰 V27 显示器", brand="Viewnest",
                category="monitors", description="27 英寸 2K 显示器，适合办公和编程。",
                tags=("显示器", "屏幕", "monitor", "2k"),
                skus=(Sku(id="mon01-black", name="黑色", price=Money(amount_minor=129900), stock=3),)),
    )
