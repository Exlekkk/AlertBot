from __future__ import annotations

BANNED = ["liquidity","MSB","OB","MB","BB","CHoCH","RAR","TAI","SMC","ICT","ABCX"]

def format_trend_message(d: dict) -> str:
    zl, zh = d["zone"]
    if d["direction"] == "long":
        text = f"📈 BTC 1H 结构转多提醒\n\n状态：\n下方关键区触发后，价格重新收回。\n1H 结构正在转多。\n\n关注区间：\n{zl:.2f} - {zh:.2f}\n\n大周期：\n{d['htf_context']}\n但本次提醒以 1H 结构变化为主。\n\n动能与热度：\n{d['momentum_desc']}\n{d['temperature_desc']}\n\n风险位：\n若跌破 {d['invalid_level']:.2f}，本轮转多结构失败。\n\n结论：\n不追价。\n等待价格回到关注区间后的反应。"
    else:
        text = f"📉 BTC 1H 结构转空提醒\n\n状态：\n上方关键区触发后，价格开始回落。\n1H 结构正在转空。\n\n关注区间：\n{zl:.2f} - {zh:.2f}\n\n大周期：\n{d['htf_context']}\n但本次提醒以 1H 结构变化为主。\n\n动能与热度：\n{d['momentum_desc']}\n{d['temperature_desc']}\n\n风险位：\n若重新站回 {d['invalid_level']:.2f}，本轮转空结构失败。\n\n结论：\n不追空。\n等待价格反抽关注区间后的承压反应。"
    return text
