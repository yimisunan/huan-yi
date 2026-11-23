"use strict";
/* METADATA
{
  "name": "story_bridge",
  "display_name": "故事桥接",
  "description": "连接本地故事页，通过Operit正式会话按需读取项目资料并生成回合。",
  "category": "Productivity",
  "enabled_by_default": true,
  "tools": [
    {
      "name": "start",
      "description": "当用户要求启动/开启故事桥接服务时，必须执行此工具；这是连接管理操作，不生成或返回故事JSON。",
      "parameters": []
    },
    {
      "name": "stop",
      "description": "停止领取新行动，已领取任务完成一次。",
      "parameters": []
    },
    {
      "name": "status",
      "description": "检查桥接真实运行状态、会话与连接错误，不调用模型、不生成剧情。",
      "parameters": []
    },
    {
      "name": "configure",
      "description": "停止状态下配置功能模型与项目工作区。",
      "parameters": [
        {
          "name": "functionType",
          "type": "string",
          "required": false,
          "description": "Operit功能模型名称，例如CHAT"
        },
        {"name":"workspacePath","type":"string","required":false,"description":"项目工作区的VFS绝对路径"},
        {"name":"endpoint","type":"string","required":false,"description":"本机故事服务地址，例如http://127.0.0.1:5000"},
        {"name":"resetSession","type":"boolean","required":false,"description":"空闲时重建桥接会话，保留旧聊天与正式存档"},
        {"name":"sessionPolicy","type":"string","required":false,"description":"continuous持续沿用；service_restart重启Python后新建；per_action每个新行动新建，重试沿用"},
        {"name":"dualStage","type":"boolean","required":false,"description":"true启用双阶段流式(v2：主模型演播+副模型后台结算)；false切换为单阶段精简(v2)"},
        {"name":"primaryModelMode","type":"string","required":false,"description":"slot跟随功能槽；fixed故事专属固定模型（不改Operit主聊天模型）"},
        {"name":"primaryProviderId","type":"string","required":false,"description":"primaryModelMode=fixed时主模型的服务商ID"},
        {"name":"primaryModelId","type":"string","required":false,"description":"primaryModelMode=fixed时主模型的模型ID"},
        {"name":"settlementFunctionType","type":"string","required":false,"description":"后台结算使用的Operit功能模型槽，默认SUMMARY，未绑定时自动回退主功能槽"},
        {"name":"settlementThinking","type":"boolean","required":false,"description":"兼容旧开关：true等价on，false等价off"},
        {"name":"settlementThinkingMode","type":"string","required":false,"description":"后台结算思考策略：auto智能自适应（首轮免思考，校验重试自动开思考，默认）、off常关（极速）、on常开（深度）"},
        {"name":"maxTurnsPerSession","type":"number","required":false,"description":"同场景会话每满N轮干净切窗以防摘要漂移，默认10（范围2～30）"}
      ]
    }
  ]
}
*/
function start(params = {}) { return ToolPkg.ipc.call('story.bridge.control', { ...params, action: 'start' }, { targetRuntime: 'main' }); }
function stop(params = {}) { return ToolPkg.ipc.call('story.bridge.control', { ...params, action: 'stop' }, { targetRuntime: 'main' }); }
function status(params = {}) { return ToolPkg.ipc.call('story.bridge.control', { ...params, action: 'status' }, { targetRuntime: 'main' }); }
function configure(params = {}) { return ToolPkg.ipc.call('story.bridge.control', { ...params, action: 'configure' }, { targetRuntime: 'main' }); }

exports.start = start;
exports.stop = stop;
exports.status = status;
exports.configure = configure;
