# GPT Image 2.5 参数规范

适用模型：`gpt-image-2.5-flare`、`gpt-image-2.5-sunburst`。

## 选择

- `flare`：速度优先，适合日常生成与快速迭代。
- `sunburst`：质量优先，适合复杂改图、主体保持、文字和精细结构。
- 用户只说 `image2.5` 时，路由到 `gpt-image-2.5-sunburst`。
- 插件全局默认仍是 `banana2.1`（`thinkingLevel=high`），本规范不会静默改默认模型。

## 接口

- 文生图：`POST {base}/v1/images/generations`，JSON。
- 改图 / 多参考：`POST {base}/v1/images/edits`，multipart。
- 鉴权：`Authorization: Bearer <API_KEY>`。
- 本地图片字段：重复使用 `image[]`，顺序必须与提示词中的 `@图1 / @图2 / @图3...` 一致；API 字段名保持不变。

文生图：

```json
{
  "model": "gpt-image-2.5-flare",
  "prompt": "完整中文提示词",
  "n": 1,
  "size": "2048x2048",
  "quality": "high",
  "output_format": "png"
}
```

多参考改图：

```text
model=gpt-image-2.5-sunburst
prompt=完整中文改图指令
n=1
size=2048x2048
quality=high
output_format=png
image[]=@目标图.png
image[]=@参考图.png
```

## 参数

- `quality`：`auto | low | medium | high | xhigh | max`；DUMIK 默认 `high`。
- `size`：`auto` 或自定义 `WIDTHxHEIGHT`。宽高均为 16 的倍数，比例在 `1:3` 到 `3:1`，单边不超过 3840；超过 `2560x1440` 属于实验尺寸。
- 常用尺寸：`1024x1024`、`1536x1024`、`1024x1536`、`2048x2048`、`2048x1152`、`3840x2160`、`2160x3840`。方图合法最大值为 `2880x2880`；3:4 基准最大值使用 `2480x3312`。
- `background`：`auto | opaque | transparent`。透明背景配 `png` 或 `webp`。
- `output_format`：`png | jpeg | webp`；DUMIK 默认 `png`。
- GPT Image 返回内容按 `data[].b64_json` 保存；若兼容接口返回 URL，执行器也可下载。

## 实测

2026-09-09 使用团队当前 API 配置完成真实兼容性测试：Flare 与 Sunburst 的文生图、双参考改图均返回 HTTP 200；官方 `image[]` 多图字段有效，`1024x1024 / medium / png` 实际像素准确。

## 官方来源

- https://developers.openai.com/api/docs/models/gpt-image-2.5-flare
- https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst
- https://developers.openai.com/api/docs/guides/image-prompting
- https://developers.openai.com/api/reference/resources/images/methods/generate
- https://developers.openai.com/api/reference/resources/images/methods/edit
