import { Composition } from 'remotion';
import { StockVideo } from './StockVideo';
import { InvestorGallery } from './components/InvestorCharacter';
import type { VideoItem, VideoProps } from './types';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition id="InvestorGallery" component={InvestorGallery} durationInFrames={150} fps={30} width={1920} height={1080}/>
      <Composition
        id="StockVideo"
        component={StockVideo}
        durationInFrames={900} // 30fps × 30s 기본 — 타임스탬프로 동적 보정
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ items: [] } as VideoProps}
        calculateMetadata={({ props }) => {
          const items = (props as VideoProps).items as VideoItem[];
          const item = items?.[0];
          if (!item) {
            return {};
          }
          const end = item.timestamps?.length
            ? item.timestamps[item.timestamps.length - 1].end
            : 30;
          // 마지막 단어 타임스탬프 + 2초 여백
          return {
            durationInFrames: Math.max(60, Math.ceil((end + 2) * 30)),
          };
        }}
      />
    </>
  );
};
