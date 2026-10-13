import { Config } from '@remotion/cli/config';
import os from 'os';

Config.setVideoImageFormat('jpeg');
Config.setCodec('h264');

// 시스템 메모리에 따른 동적 Concurrency 할당
// M4 MBP 48GB 테스트 시: 4 권장 / Mac mini 24GB 운영 시: 2 권장
const totalMemoryGB = os.totalmem() / (1024 * 1024 * 1024);
Config.setConcurrency(Number(process.env.REMOTION_CONCURRENCY) || (totalMemoryGB > 32 ? 4 : 2));

// Chromium GPU 가속 (ANGLE 백엔드 — macOS에서 WebGL 안정화)
Config.setChromiumOpenGlRenderer('angle');

// ffmpeg hwaccel 자동 선택 (hardware decode)
Config.setHardwareAcceleration('if-possible');

/**
 * VideoToolbox 하드웨어 인코더 전달
 *
 * NOTE: README 의 `Config.overrideFfmpegCommand((defaultArgs) => ...)` 는
 * Remotion 4.x 시그니처와 맞지 않습니다. 4.x 의 훅은
 *   (info: { type: 'pre-stitcher' | 'stitcher', args: string[] }) => string[]
 * 형태이므로 info.args 를 매핑해야 합니다.
 *
 * libx264(software) → h264_videotoolbox(hardware)로 치환해
 * Apple Silicon 의 Media Engine 을 사용합니다.
 */
Config.overrideFfmpegCommand(({ type, args }) => {
  if (process.env.DEBUG_FFMPEG_ARGS === '1') {
    console.log(`[ffmpeg:${type}]`, args.join(' '));
  }
  const useVideoToolbox = process.platform === 'darwin' && process.env.REMOTION_SOFTWARE_ENCODING !== '1';
  return useVideoToolbox ? args.map((arg) => (arg === 'libx264' ? 'h264_videotoolbox' : arg)) : args;
});
