#include <KLocalizedString>
#include <QApplication>
#include <QtConcurrent>
#include <cstdio>
#include <emscripten.h>

static int checks = 0;
static void equal(const QString &actual, const QString &expected) {
    ++checks;
    if (actual != expected) {
        const auto message = QStringLiteral("check %1: expected [%2], got [%3]")
                                 .arg(checks)
                                 .arg(expected, actual)
                                 .toUtf8();
        std::fprintf(stderr, "%s\n", message.constData());
        EM_ASM({ fetch('/__probe_result?status=' + encodeURIComponent('FAIL: ' + UTF8ToString($0)));}, message.constData());
        std::abort();
    }
}

int main(int argc, char **argv) {
    qputenv("XDG_DATA_DIRS", "/probe/share");
    QApplication app(argc, argv);
    KLocalizedString::setApplicationDomain("sdk-i18n");
    KLocalizedString::addDomainLocaleDir("sdk-i18n", QStringLiteral("/probe/share/locale"));
    KLocalizedString::setLanguages({QStringLiteral("zh_CN"), QStringLiteral("en_US")});
    equal(i18n("Probe"), QString::fromUtf8("探针"));
    equal(i18nc("verb", "Open"), QString::fromUtf8("打开"));
    equal(i18nc("adjective", "Open"), QString::fromUtf8("开放"));
    equal(i18np("%1 item", "%1 items", 5), QString::fromUtf8("5 项"));
    equal(i18n("Script %1", QStringLiteral("value")), QStringLiteral("scripted:value"));
    KLocalizedString::setLanguages({QStringLiteral("ru"), QStringLiteral("en_US")});
    equal(i18n("Probe"), QString::fromUtf8("Проба"));
    equal(i18np("%1 item", "%1 items", 1), QStringLiteral("1 one"));
    equal(i18np("%1 item", "%1 items", 2), QStringLiteral("2 few"));
    equal(i18np("%1 item", "%1 items", 5), QStringLiteral("5 many"));
    equal(i18np("%1 item", "%1 items", 21), QStringLiteral("21 one"));
    KLocalizedString::setLanguages({QStringLiteral("ar"), QStringLiteral("en_US")});
    for (auto pair : {qMakePair(0, "zero"), qMakePair(1, "one"), qMakePair(2, "two"),
                      qMakePair(3, "few"), qMakePair(11, "many"), qMakePair(100, "other")})
        equal(i18np("%1 item", "%1 items", pair.first),
              QString::number(pair.first) + QLatin1Char(' ') + QLatin1String(pair.second));
    KLocalizedString::setLanguages(
        {QStringLiteral("de"), QStringLiteral("fr"), QStringLiteral("en_US")});
    equal(i18n("Probe"), QStringLiteral("Probe-DE"));
    equal(i18n("French only"), QStringLiteral("Seulement français"));
    equal(i18n("Missing"), QStringLiteral("Missing"));
    KLocalizedString::setLanguages({QStringLiteral("en_US"), QStringLiteral("fr")});
    equal(i18n("French only"), QStringLiteral("French only"));
    KLocalizedString::setLanguages({QStringLiteral("zh_CN"), QStringLiteral("en_US")});
    equal(i18n("Probe"), QString::fromUtf8("探针"));
    auto future = QtConcurrent::run([] { return i18nc("verb", "Open"); });
    future.waitForFinished();
    equal(future.result(), QString::fromUtf8("打开"));
    std::printf(
        "SDK_I18N_OK: %d real KI18n context/plural/fallback/cache/Transcript/thread checks\n",
        checks);
    EM_ASM({ fetch('/__probe_result?status=SDK_I18N_OK');});
    return app.exec();
}
