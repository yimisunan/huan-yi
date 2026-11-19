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
        {"name":"sessionPolicy","type":"string","required":false,"description":"continuous持续沿用；service_restart重启Python后新建；per_action每个新行动新建，重试沿用"}
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
