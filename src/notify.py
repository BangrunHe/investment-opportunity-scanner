"""提醒输出：控制台打印 + 可选网易邮箱 SMTP 发送。"""

import os
import smtplib
from email.header import Header
from email.mime.text import MIMEText

from . import config


def send_console(alerts, analyses):
    """在控制台打印分析结论与限额/卖出提醒。"""
    print("\n========== 多 AI agent 分析结果 ==========")
    for a in analyses:
        weekly = a.get("weekly_amount") or 0.0
        print(f"\n【{a['name']}】信号={a.get('signal')} 每周定投={weekly:.2f}元")
        est = a.get("estimated_cycle_weeks")
        if est:
            print(f"  预估加仓周期：{est} 周（置信度 {a.get('confidence')}）")
        print(f"  分析：{a.get('reasoning', '')}")
        risks = a.get("risks") or []
        if risks:
            print(f"  风险：{'；'.join(risks)}")

    print("\n========== 限额 / 卖出提醒 ==========")
    if not alerts:
        print("（无超限提醒）")
    for al in alerts:
        tag = "停止加仓" if al["level"] == "critical" else "提醒"
        print(f"[{tag}] {al['message']}")


def build_report(subject, analyses, alerts) -> str:
    """生成纯文本邮件正文。"""
    lines = [f"# {subject}", ""]
    for a in analyses:
        weekly = a.get("weekly_amount") or 0.0
        lines.append(f"{a['name']}：信号={a.get('signal')} 每周定投={weekly:.2f}元")
        est = a.get("estimated_cycle_weeks")
        if est:
            lines.append(f"  预估加仓周期：{est} 周（{a.get('confidence')}）")
        lines.append(f"  分析：{a.get('reasoning', '')}")
        risks = a.get("risks") or []
        if risks:
            lines.append(f"  风险：{'；'.join(risks)}")
        lines.append("")

    if alerts:
        lines.append("限额/卖出提醒：")
        for al in alerts:
            lines.append(f"  - {al['message']}")
    else:
        lines.append("（无超限提醒）")
    return "\n".join(lines)


def send_email(subject: str, body: str) -> None:
    """通过网易邮箱 SMTP 发送邮件（需配置环境变量授权码）。"""
    username = os.environ.get(config.EMAIL["username_env"])
    password = os.environ.get(config.EMAIL["password_env"])
    to = os.environ.get(config.EMAIL["to_env"])
    if not (username and password and to):
        raise RuntimeError(
            "邮件未配置：请设置 EMAIL_USERNAME / EMAIL_PASSWORD(授权码) / EMAIL_TO"
        )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = username
    msg["To"] = to

    if config.EMAIL["use_ssl"]:
        server = smtplib.SMTP_SSL(config.EMAIL["smtp_host"], config.EMAIL["smtp_port"])
    else:
        server = smtplib.SMTP(config.EMAIL["smtp_host"], config.EMAIL["smtp_port"])
    try:
        server.login(username, password)
        server.sendmail(username, [to], msg.as_string())
    finally:
        server.quit()
