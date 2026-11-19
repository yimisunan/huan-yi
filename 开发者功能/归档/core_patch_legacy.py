# patch_file_功能简写.py
# 自动修复 main_template.html 中 parseDeepBodyText 解析Bug
# 严格保留原内容作为 OLD_TEXT，强制生成 .bak 备份，禁止任何手动粘贴

import os
import shutil

def main():
    target_file = "main_template.html"
    
    if not os.path.exists(target_file):
        print(f"[错误] 找不到目标文件：{target_file}")
        print("请确认本脚本与 main_template.html 位于同一目录后重新运行。")
        return

    # 1. 强制备份（绝对禁止跳过）
    bak_file = target_file + ".bak"
    shutil.copy2(target_file, bak_file)
    print(f"[√] 已自动备份原文件 → {bak_file}")

    # 2. 读取完整内容
    with open(target_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 3. 保留被替换的原内容（严格要求）
    OLD_TEXT = '''function parseDeepBodyText(text) {
    const result = {};
    text.split(/【/).forEach(section => {
        const nameMatch = section.match(/】\\s*(\\S+)/);
        if (!nameMatch) return;
        const name = nameMatch[1];
        if (['沈知韫','徐念薇','苏婉青'].includes(name)) {
            result[name] = {
                shame: (section.match(/羞耻度：(\\d+)/) || [])[1] || 100,
                discovery: (section.match(/深层发现：([\\s\\S]*?)身体状态：/) || [])[1] || '（待解锁）',
                bodyStatus: (section.match(/身体状态：([\\s\\S]*?)(?=\\n【|$)/) || [])[1] || '当前无异常记录'
            };
        }
    });
    return result;
}'''

    # 4. 新修复内容（精准修正 name 提取逻辑）
    NEW_TEXT = '''function parseDeepBodyText(text) {
    const result = {};
    text.split(/【/).forEach(section => {
        // 修复：正确提取【名字】中的名字（原逻辑错误地把“羞耻度”当成了名字）
        const nameMatch = section.match(/^([^】]+)】/);
        if (!nameMatch) return;
        const name = nameMatch[1].trim();
        if (['沈知韫','徐念薇','苏婉青'].includes(name)) {
            result[name] = {
                shame: (section.match(/羞耻度：(\\d+)/) || [])[1] || 100,
                discovery: (section.match(/深层发现：([\\s\\S]*?)身体状态：/) || [])[1] || '（待解锁）',
                bodyStatus: (section.match(/身体状态：([\\s\\S]*?)(?=\\n【|$)/) || [])[1] || '当前无异常记录'
            };
        }
    });
    return result;
}'''

    # 5. 安全检查 + 精准替换
    if OLD_TEXT not in content:
        print("[错误] 未在文件中找到完全匹配的原始函数代码。")
        print("可能原因：文件已被手动修改，或版本不一致。")
        print("已保留 .bak 备份，未进行任何写入，请检查后重试。")
        return

    new_content = content.replace(OLD_TEXT, NEW_TEXT)

    # 6. 写回文件
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(new_content)

    print("[√] 修复完成！parseDeepBodyText 已更新。")
    print("[√] 深层档案与身体状态页现在会正确读取最新羞耻度。")
    print(f"[提示] 如需回滚，直接把 {bak_file} 改回 main_template.html 即可。")

if __name__ == "__main__":
    main()