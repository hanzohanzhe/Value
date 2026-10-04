"""Public release status; links are added only after actual release verification."""
def pages(w):
    t=w.t
    title=t('Install from value.ac','从 value.ac 安装')
    intro=t('The 2026-10-03-rc1 candidate is an internal review artifact. No verified public software Release URL is configured.','2026-10-03-rc1 为内部评审候选；目前尚未配置经核验的公开软件 Release 地址。')
    body=w.heading('VALUE / 2026-10-03-rc1',title,intro)
    body+=w.note(t('Choose, download, install','选择、下载、安装'),t('Choose your platform on value.ac. The download links point to the exact full installer in GitHub Releases. Extract the package, run its installer and then launch VALUE on your computer. Each Full package includes its own runtime; public downloads are still pending.','在 value.ac 选择平台，下载链接直达 GitHub Releases 中对应的完整安装包。解压后运行安装器，再在自己的电脑上启动 VALUE。Full 包自带环境；公开下载仍待发布。'))
    body+=w.note(t('Download status','下载状态'),t('Public installers are not available from this website yet. A source repository alone does not establish a software release. Platform installers, checksums and installation instructions will be linked after their actual release files and licences are verified.','本站暂未提供公开安装包。源码仓库本身不代表软件已发布；实际版本文件与许可核验后，再接入对应平台安装包、校验和及安装说明。'))
    body+='<p>'+w.a('methodology','Read the methodology','阅读完整方法学')+' · '+w.a('releases','Software availability','软件发布状态')+'</p>'
    return [('release-check',title,intro,body)]
