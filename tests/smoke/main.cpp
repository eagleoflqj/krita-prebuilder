#include <KConfigGroup>
#include <KFileSystemType>
#include <KFormat>
#include <KListOpenFilesJob>
#include <KPluginFactory>
#include <KProcessList>
#include <KSharedConfig>
#include <QApplication>
#include <QDateTime>
#include <QLabel>
#include <QTimeZone>
#include <QTimer>
#include <emscripten.h>

int main(int argc, char **argv) {
    auto *app = new QApplication(argc, argv);
    auto config = KSharedConfig::openConfig();
    auto *label = new QLabel(QStringLiteral("SDK static Qt + KDE smoke"));
    label->show();
    // Force the KDE factory implementation into this cache-warming link.
    auto *factory = new KPluginFactory;
    factory->setParent(app);
    if (!config)
        return 1;
    KConfigGroup group(config, "sdk-smoke");
    for (int offset : {0, 19800, -12600, 19815}) {
        const QDateTime original(QDate(2026, 1, 2), QTime(3, 4, 5, 678),
                                 QTimeZone::fromSecondsAheadOfUtc(offset));
        group.writeEntry("datetime", original);
        const auto restored = group.readEntry("datetime", QDateTime());
        if (restored != original || restored.offsetFromUtc() != offset)
            qFatal("KConfig UTC/fixed-offset datetime roundtrip failed");
        if (KFormat()
                .formatTime(original, QLocale::ShortFormat, KFormat::AddTimezoneAbbreviation)
                .isEmpty())
            qFatal("KFormat time without timezone backend failed");
    }
    const QDateTime fallback(QDate(2000, 1, 1), QTime(0, 0), QTimeZone::UTC);
    group.writeEntry("named-zone",
                     QStringList{"2026", "1", "2", "3", "4", "5", "America/New_York"});
    if (group.readEntry("named-zone", fallback) != fallback)
        qFatal("Unsupported named timezone was silently reinterpreted");
    config->checkUpdate(QStringLiteral("sdk-smoke"), QStringLiteral("unavailable.upd"));
    if (!KProcessList::processInfoList().isEmpty() || KProcessList::processInfo(1).isValid())
        qFatal("Unsupported host processes were simulated");
    if (KFileSystemType::fileSystemType(QStringLiteral("/")) != KFileSystemType::Unknown)
        qFatal("Browser filesystem was reported as a host filesystem");
    auto *job = new KListOpenFilesJob(QStringLiteral("/"));
    job->setParent(app);
    QObject::connect(job, &KJob::result, app, [](KJob *result) {
        if (result->error() != static_cast<int>(KListOpenFilesJob::Error::NotSupported))
            qFatal("Host file enumeration did not report NotSupported");
        EM_ASM({
            document.title = 'SDK_SMOKE_OK';
            document.getElementById('status').textContent = 'SDK_SMOKE_OK';
            if (new URLSearchParams(location.search).has('test'))
                fetch('/__probe_result?status=SDK_SMOKE_OK');
        });
    });
    job->start();
#ifdef QT_HAVE_EMSCRIPTEN_ASYNCIFY
    return app->exec();
#else
    return config ? 0 : 1;
#endif
}
