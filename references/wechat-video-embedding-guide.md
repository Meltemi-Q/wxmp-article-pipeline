# 微信公众平台视频嵌入与素材上传避坑完全指南

本指南总结了微信公众号草稿箱正文中嵌入实测视频的真实底层机制与血泪踩坑经验，避免后续重复踩坑。

---

## 一、核心真相：微信草稿箱的视频不是 `<video>` 标签！

### 1. 常见致命误区
很多人（以及大部分默认 AI）以为向微信草稿箱 HTML 传 `<video src="..." controls></video>` 或者 `<video mediawidget_nodeid="...">` 就能播放。
**事实**：微信公众号后台自带极严格的 HTML Sanitizer，非微信原生白名单标签会被直接过滤清洗，导致读者和后台看到的视频直接“蒸发消失”。

### 2. 微信官方草稿箱真正的视频渲染格式
微信公众平台在富文本中展示原生视频卡片播放器，必须使用微信专属的 `iframe` 格式：

```html
<p style="text-align: center; margin: 24px 0 8px;">
  <iframe class="video_iframe" 
          data-vidtype="2" 
          data-mpvid="{vid}" 
          src="https://v.qq.com/iframe/preview.html?vid={vid}" 
          frameborder="0" 
          allowfullscreen="" 
          style="width: 100%; height: 375px; border-radius: 8px;">
  </iframe>
</p>
<p style="text-align: center; color: #999; font-size: 13px; margin: 0 0 20px;">
  👆 视频：实测演示说明
</p>
```

---

## 二、素材上传与 vid 获取全流程

嵌入视频不能只拿 `media_id`，必须拿到微信内部生成的 **`vid`**（如 `apiv_4678493344736624641`）：

1. **第一步：上传本地 MP4 到永久素材库**
   - 接口：`POST https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=video`
   - 表单字段：
     - `media=@video.mp4`
     - `description={"title": "视频标题", "introduction": "视频简介"}`
   - 返回：`{"media_id": "phWtp..."}`
   
2. **第二步：调用素材详情接口提取 `vid`**
   - 接口：`POST https://api.weixin.qq.com/cgi-bin/material/get_material?access_token={token}`
   - 请求体：`{"media_id": "phWtp..."}`
   - 返回 JSON 中包含核心字段：`"vid": "apiv_xxxxxxxx"`
   
3. **第三步：将 `vid` 填入 `video_iframe` 组件并嵌入正文**
   - 正文内使用 `data-mpvid="{vid}"` 与 `src="https://v.qq.com/iframe/preview.html?vid={vid}"`。

---

## 三、避坑铁律与工程防御机制

### 1. 视频体积与转码规范（防 45001 与 -1 system error）
- 微信永久素材接口对视频大小极其敏感。超过 20MB-30MB 的高码率视频，经常直接报错 `errcode: -1 system error` 或超时中断。
- **最佳实践**：上传前一律用 `ffmpeg` 压制一份 720p/H.264 优化版：
  ```bash
  ffmpeg -y -i input.mp4 -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k output_wx.mp4
  ```
  控制文件大小在 5MB~15MB 之间，既保证电影级画质，又确保微信接口秒传秒过。

### 2. 缓存与重试机制（防止重复上传与接口抖动）
- 微信永久素材一经上传成功就会永久保留在素材库中。
- 脚本必须维护 `/tmp/wx_video_cache.json`，根据 `文件名 + 文件大小` 记录已上传的 `media_id`。命中缓存直接复用，避免每次推送重复上传几十兆大文件。
- 网络偶发异常时，自动带退避重试（最多 3 次，间隔 3 秒）。

### 3. 正文精准插槽：`[VIDEO]` 标记
- **严禁**无脑把视频直接硬塞到文章最末尾。
- 在 Markdown 正文中，在对应的情境段落（如“运镜确实牛，大家戳下面感受一下”）下方直接写一行：
  ```markdown
  [VIDEO]
  ```
- 渲染脚本检测到 `[VIDEO]` 或 `<p>[VIDEO]</p>` 时，自动将视频播放器 iframe 原地替换进去，图文影音浑然一体。
