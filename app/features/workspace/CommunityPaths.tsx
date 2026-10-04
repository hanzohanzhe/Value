"use client";

import { useId } from "react";
import "./community-paths.css";

export type CommunityPath = "reproduce" | "data" | "module" | "function";

export type CommunityPathsProps = {
  activePath: CommunityPath | null;
  onSelect: (path: CommunityPath) => void;
};

export const COMMUNITY_PATHS: ReadonlyArray<{
  id: CommunityPath;
  label: string;
  description: string;
  capability: string;
}> = [
  {
    id: "reproduce",
    label: "reproduce from existing data",
    description: "使用已有数据与模型设置，复现一项研究。",
    capability: "选择已保存的基线，创建独立 Study，再检查、运行并比较。",
  },
  {
    id: "data",
    label: "add your new data",
    description: "导入并校验自己的数据，保留方法，比较变化。",
    capability: "安装独立数据包，沿用基线方法创建新 Study，检查后运行。",
  },
  {
    id: "module",
    label: "Edit module",
    description: "修改现有模块的公式、算法或规则，并测试影响。",
    capability: "安装与选择兼容模块；界面公式编辑限于已开放的受限公式。",
  },
  {
    id: "function",
    label: "add new function to VALUE",
    description: "增加模型能力，同时补齐所需数据、模块和验证。",
    capability: "安装扩展包；新能力由作者在本地实现、测试并打包。",
  },
];

export function CommunityHome({ activePath, onSelect }: CommunityPathsProps) {
  const descriptionId = useId();

  return (
    <section className="community-home" aria-label="VALUE research tasks">
      <header className="community-home-heading">
        <span>VALUE</span>
        <h2>选择研究任务</h2>
        <p>按当前任务选择路径，使用同一套研究配置、运行与结果。</p>
      </header>
      <div className="community-path-grid">
        {COMMUNITY_PATHS.map((path) => {
          const detailId = descriptionId + "-" + path.id;
          return (
            <button
              type="button"
              className="community-path-card"
              key={path.id}
              aria-label={path.label}
              aria-describedby={detailId}
              aria-pressed={activePath === path.id}
              onClick={() => onSelect(path.id)}
              data-community-path={path.id}
            >
              <span className="community-path-title" lang="en">{path.label}</span>
              <span className="community-path-description">{path.description}</span>
              <span className="community-path-capability" id={detailId}>
                <span>当前支持</span>
                {path.capability}
              </span>
              <span className="community-path-open" aria-hidden="true">打开路径 →</span>
            </button>
          );
        })}
      </div>
      <p className="community-home-note">四条路径可以切换，无需逐级解锁。完整模块和新能力在本地编辑、测试后，以版本包安装。</p>
    </section>
  );
}

export function CommunityPathPicker({ activePath, onSelect }: CommunityPathsProps) {
  return (
    <nav className="community-path-picker" aria-label="VALUE research tasks">
      {COMMUNITY_PATHS.map((path) => (
        <button
          key={path.id}
          type="button"
          aria-pressed={activePath === path.id}
          onClick={() => onSelect(path.id)}
          data-community-path={path.id}
          lang="en"
        >
          {path.label}
        </button>
      ))}
    </nav>
  );
}
