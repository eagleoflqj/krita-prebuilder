#include <KCategorizedSortFilterProxyModel>
#include <KColorScheme>
#include <KColorUtils>
#include <KCompletion>
#include <KConfigGroup>
#include <KDateTimeEdit>
#include <KLineEdit>
#include <KLocalizedString>
#include <KSharedConfig>
#include <QApplication>
#include <QBuffer>
#include <QImage>
#include <QLabel>
#include <QPainter>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQuickItem>
#include <QStandardItemModel>
#include <QSvgRenderer>
#include <QTextCodec>
#include <QTimeZone>
#include <exiv2/exiv2.hpp>
#include <fontconfig/fontconfig.h>
#include <ft2build.h>
#include <quazip.h>
#include <quazipfile.h>
#include <rhi/qshaderbaker.h>
#include FT_FREETYPE_H
#include <Eigen/Dense>
#include <array>
#include <boost/optional.hpp>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <emscripten.h>
#include <fribidi.h>
#include <functional>
#include <gsl/gsl_linalg.h>
#include <hb-ft.h>
#include <immer/vector.hpp>
#include <lager/state.hpp>
#include <lcms2.h>
#include <linebreak.h>
#include <numeric>
#include <png.h>
#include <vector>
#include <xsimd/xsimd.hpp>
#include <zlib.h>
#include <zug/reducing/first.hpp>
#include <zug/transduce.hpp>
#include <zug/transducer/map.hpp>

static void require(bool condition, const char *message) {
    if (!condition)
        qFatal("Dependency probe: %s", message);
}

static void imageAndArchive() {
    const QByteArray payload("static SDK zip and compression roundtrip");
    std::array<unsigned char, 256> compressed{}, restored{};
    uLongf compressedSize = compressed.size(), restoredSize = restored.size();
    require(compress2(compressed.data(), &compressedSize,
                      reinterpret_cast<const Bytef *>(payload.constData()), payload.size(),
                      9) == Z_OK,
            "zlib compress");
    require(uncompress(restored.data(), &restoredSize, compressed.data(), compressedSize) == Z_OK &&
                QByteArray(reinterpret_cast<char *>(restored.data()), restoredSize) == payload,
            "zlib roundtrip");

    const std::array<unsigned char, 8> pixels{255, 0, 0, 255, 0, 255, 0, 128};
    png_image png{};
    png.version = PNG_IMAGE_VERSION;
    png.width = 2;
    png.height = 1;
    png.format = PNG_FORMAT_RGBA;
    png_alloc_size_t size = 0;
    require(png_image_write_to_memory(&png, nullptr, &size, 0, pixels.data(), 0, nullptr),
            "PNG encoded size");
    std::vector<unsigned char> data(size);
    require(png_image_write_to_memory(&png, data.data(), &size, 0, pixels.data(), 0, nullptr),
            "PNG encode");
    png_image decoded{};
    decoded.version = PNG_IMAGE_VERSION;
    require(png_image_begin_read_from_memory(&decoded, data.data(), size), "PNG header");
    decoded.format = PNG_FORMAT_RGBA;
    std::array<unsigned char, 8> output{};
    require(png_image_finish_read(&decoded, nullptr, output.data(), 0, nullptr) && output == pixels,
            "PNG pixels");
    png_image_free(&decoded);
    auto qtImage = QImage::fromData(data.data(), size, "PNG");
    require(qtImage.size() == QSize(2, 1) && qtImage.pixelColor(0, 0) == QColor(Qt::red),
            "Qt PNG shares external codec");

    QuaZip zip(QStringLiteral("/tmp/probe.kra"));
    require(zip.open(QuaZip::mdCreate), "ZIP create");
    QuaZipFile member(&zip);
    require(member.open(QIODevice::WriteOnly, QuaZipNewInfo(QStringLiteral("maindoc.xml"))),
            "ZIP member create");
    require(member.write(payload) == payload.size(), "ZIP member write");
    member.close();
    zip.close();
    require(zip.open(QuaZip::mdUnzip) && zip.setCurrentFile(QStringLiteral("maindoc.xml")),
            "ZIP reopen");
    require(member.open(QIODevice::ReadOnly) && member.readAll() == payload, "ZIP roundtrip");
    member.close();
    zip.close();

    cmsHPROFILE srgb = cmsCreate_sRGBProfile(), xyz = cmsCreateXYZProfile();
    require(srgb && xyz, "ICC profile creation");
    auto transform =
        cmsCreateTransform(srgb, TYPE_RGB_DBL, xyz, TYPE_XYZ_DBL, INTENT_RELATIVE_COLORIMETRIC, 0);
    require(transform != nullptr, "ICC transform creation");
    double white[3]{1, 1, 1}, result[3]{};
    cmsDoTransform(transform, white, result, 1);
    require(std::abs(result[1] - 1.0) < 0.01, "ICC white point");
    cmsDeleteTransform(transform);
    cmsCloseProfile(srgb);
    cmsCloseProfile(xyz);

    Exiv2::ExifData exif, exifResult;
    exif["Exif.Image.Artist"] = "Wasm SDK";
    Exiv2::Blob blob;
    Exiv2::ExifParser::encode(blob, Exiv2::littleEndian, exif);
    Exiv2::ExifParser::decode(exifResult, blob.data(), blob.size());
    require(exifResult["Exif.Image.Artist"].toString() == "Wasm SDK", "EXIF roundtrip");
    require(Exiv2::XmpParser::initialize(), "XMP initialize");
    Exiv2::XmpData xmp, xmpResult;
    xmp["Xmp.dc.format"] = "image/png";
    std::string packet;
    require(Exiv2::XmpParser::encode(packet, xmp) == 0 &&
                Exiv2::XmpParser::decode(xmpResult, packet) == 0 &&
                xmpResult["Xmp.dc.format"].toString() == "image/png",
            "XMP/Expat roundtrip");
    Exiv2::XmpParser::terminate();
    bool caught = false;
    try {
        auto invalid =
            Exiv2::ImageFactory::open(reinterpret_cast<const Exiv2::byte *>("invalid"), 7);
        (void)invalid;
    } catch (const Exiv2::Error &) {
        caught = true;
    }
    require(caught, "Exiv2 C++ exception propagation");
}

static void textAndFonts() {
    FT_Library library{};
    FT_Face face{};
    require(FT_Init_FreeType(&library) == 0, "FreeType init");
    require(FT_New_Face(library, "/fonts/DejaVuSans.ttf", 0, &face) == 0, "FreeType font load");
    require(FT_Set_Char_Size(face, 0, 20 * 64, 72, 72) == 0, "FreeType size");
    require(FT_Load_Char(face, 'A', FT_LOAD_RENDER) == 0 && face->glyph->bitmap.width > 0,
            "FreeType rasterization");
    auto *font = hb_ft_font_create_referenced(face);
    auto *buffer = hb_buffer_create();
    hb_buffer_add_utf8(buffer, "سلام", -1, 0, -1);
    hb_buffer_guess_segment_properties(buffer);
    hb_shape(font, buffer, nullptr, 0);
    unsigned count = 0;
    auto *glyphs = hb_buffer_get_glyph_infos(buffer, &count);
    require(count > 0 && count <= 4, "HarfBuzz Arabic glyph count");
    for (unsigned i = 0; i < count; ++i)
        require(glyphs[i].codepoint != 0, "HarfBuzz glyph coverage");
    hb_buffer_destroy(buffer);
    hb_font_destroy(font);
    FT_Done_Face(face);
    FT_Done_FreeType(library);

    auto *config = FcInitLoadConfigAndFonts();
    require(config != nullptr, "Fontconfig default configuration");
    auto *pattern = FcNameParse(reinterpret_cast<const FcChar8 *>("DejaVu Sans"));
    require(FcConfigSubstitute(config, pattern, FcMatchPattern), "Fontconfig substitute");
    FcDefaultSubstitute(pattern);
    FcResult matchResult{};
    auto *match = FcFontMatch(config, pattern, &matchResult);
    FcChar8 *filename{};
    require(match && FcPatternGetString(match, FC_FILE, 0, &filename) == FcResultMatch &&
                QString::fromUtf8(reinterpret_cast<const char *>(filename))
                    .startsWith(QStringLiteral("/fonts/")),
            "Fontconfig real font match");
    FcPatternDestroy(match);
    FcPatternDestroy(pattern);
    FcConfigDestroy(config);

    const FriBidiChar logical[]{'a', ' ', 0x05d0, 0x05d1, 0x05d2};
    FriBidiChar visual[5]{};
    FriBidiParType direction = FRIBIDI_PAR_LTR;
    require(fribidi_log2vis(logical, 5, &direction, visual, nullptr, nullptr, nullptr) != 0 &&
                visual[2] == 0x05d2 && visual[4] == 0x05d0,
            "FriBidi mixed direction");
    init_linebreak();
    char breaks[3]{};
    set_linebreaks_utf8(reinterpret_cast<const utf8_t *>("a b"), 3, "en", breaks);
    require(breaks[1] == LINEBREAK_ALLOWBREAK, "Unicode line breaking");
}

static void templatesAndKde() {
    Eigen::Matrix2d matrix;
    matrix << 2, 0, 0, 4;
    require((matrix.inverse() * matrix).isApprox(Eigen::Matrix2d::Identity()),
            "Eigen matrix inverse");
    double values[]{2, 0, 0, 4};
    auto gslMatrix = gsl_matrix_view_array(values, 2, 2);
    auto *permutation = gsl_permutation_alloc(2);
    int sign{};
    require(gsl_linalg_LU_decomp(&gslMatrix.matrix, permutation, &sign) == 0 &&
                std::abs(gsl_linalg_LU_det(&gslMatrix.matrix, sign) - 8) < 1e-9,
            "GSL decomposition");
    gsl_permutation_free(permutation);
    const auto original = immer::vector<int>{1, 2};
    auto extended = original.push_back(3);
    require(original.size() == 2 && extended[2] == 3, "Immer persistence");
    lager::state<int, lager::automatic_tag> state{2};
    state.set(7);
    require(state.get() == 7, "Lager state update");
    const std::vector<int> numbers{1, 2, 3};
    auto sum = zug::transduce(zug::map([](int n) { return n * 2; }), std::plus<int>{}, 0, numbers);
    require(sum == 12, "Zug transducer");
    boost::optional<int> optional{sum};
    require(optional.value() == 12, "Boost headers");
    std::vector<float, xsimd::aligned_allocator<float, 16>> aligned{1, 2};
    require(reinterpret_cast<uintptr_t>(aligned.data()) % 16 == 0, "xsimd aligned storage");
    auto config = KSharedConfig::openConfig(QStringLiteral("dependency-smoke"));
    KConfigGroup group(config, "smoke");
    group.writeEntry("value", 42);
    require(group.readEntry("value", 0) == 42, "KConfig");
    const QColor storedColor(12, 34, 56, 78);
    const QFont storedFont(QStringLiteral("DejaVu Sans"), 13, QFont::DemiBold, true);
    group.writeEntry("guiColor", storedColor);
    group.writeEntry("guiFont", storedFont);
    require(group.readEntry("guiColor", QColor()) == storedColor,
            "KConfig precompiled GUI color registration");
    const QFont restoredFont = group.readEntry("guiFont", QFont());
    require(restoredFont.family() == storedFont.family() && restoredFont.pointSize() == 13 &&
                restoredFont.weight() == storedFont.weight() && restoredFont.italic(),
            "KConfig precompiled GUI font registration");
    KCompletion completion;
    completion.addItem(QStringLiteral("krita"));
    require(completion.makeCompletion(QStringLiteral("kri")) == QStringLiteral("krita"),
            "KCompletion");
    KLineEdit edit;
    edit.setText(QStringLiteral("SDK"));
    require(edit.text() == QStringLiteral("SDK"), "KWidgetsAddons");
    KDateTimeEdit dateEdit;
    for (int offset : {0, 19800, -12600, 19815}) {
        dateEdit.setTimeZone(QTimeZone::fromSecondsAheadOfUtc(offset));
        require(dateEdit.timeZone().fixedSecondsAheadOfUtc() == offset,
                "KWidgetsAddons UTC/fixed-offset zones");
    }
    require(KColorUtils::luma(QColor(Qt::white)) > 0.99, "KGuiAddons");
    require(i18np("%1 layer", "%1 layers", 2).contains(QStringLiteral("2")), "KI18n plural");
    KColorScheme scheme(QPalette::Active);
    require(scheme.background().color().isValid(), "KColorScheme");
    QStandardItemModel model;
    model.appendRow(new QStandardItem(QStringLiteral("a")));
    KCategorizedSortFilterProxyModel proxy;
    proxy.setSourceModel(&model);
    require(proxy.rowCount() == 1, "KItemViews");
    require(QTextCodec::codecForName("UTF-8")->toUnicode("Krita") == QStringLiteral("Krita"),
            "Qt Core5Compat");
    QSvgRenderer svg(QByteArray(
        "<svg xmlns='http://www.w3.org/2000/svg' width='2' height='2'><rect width='2' height='2' fill='red'/></svg>"));
    QImage canvas(2, 2, QImage::Format_ARGB32);
    canvas.fill(Qt::transparent);
    QPainter painter(&canvas);
    svg.render(&painter);
    painter.end();
    require(canvas.pixelColor(0, 0) == QColor(Qt::red), "Qt SVG rendering");
}

static void qmlAndQuick() {
    QShaderBaker baker;
    baker.setSourceString(
        "#version 440\nlayout(location = 0) in vec4 position;\nvoid main() { gl_Position = position; }\n",
        QShader::VertexStage);
    baker.setGeneratedShaderVariants({QShader::StandardShader});
    baker.setGeneratedShaders({{QShader::SpirvShader, QShaderVersion(100)}});
    const auto shader = baker.bake();
    if (!shader.isValid())
        qFatal("ShaderTools dependency probe: %s", qPrintable(baker.errorMessage()));
    require(shader.stage() == QShader::VertexStage, "ShaderTools SPIR-V compilation");
    qputenv("QT_QUICK_CONTROLS_STYLE", "Basic");
    QQmlEngine engine;
    QQmlComponent component(&engine,
                            QUrl(QStringLiteral("qrc:/qt/qml/SdkDependencyProbe/Probe.qml")));
    std::unique_ptr<QObject> object(component.create());
    if (!object)
        qFatal("QML dependency probe: %s", qPrintable(component.errorString()));
    require(qobject_cast<QQuickItem *>(object.get()) != nullptr, "Qt Quick item creation");
    require(object->property("result").toInt() == 42, "QML property binding and Quick Layouts");
    require(object->property("buttonText").toString() == QStringLiteral("SDK Quick"),
            "Static Quick Controls plugin");
}

int main(int argc, char **argv) {
    qInstallMessageHandler([](QtMsgType type, const QMessageLogContext &, const QString &message) {
        const auto text = message.toUtf8();
        EM_ASM({ fetch('/__probe_log?message=' + encodeURIComponent(UTF8ToString($0))); }, text.constData());
        if (type == QtFatalMsg)
            EM_ASM({ fetch('/__probe_result?status=' + encodeURIComponent('FAIL: ' + UTF8ToString($0))); }, text.constData());
    });
    std::puts("SDK probe: QApplication");
    auto *app = new QApplication(argc, argv);
    KLocalizedString::setApplicationDomain("sdk-deps");
    std::puts("SDK probe: image/archive/color");
    imageAndArchive();
    std::puts("SDK probe: fonts/text");
    textAndFonts();
    std::puts("SDK probe: templates/KDE");
    templatesAndKde();
    std::puts("SDK probe: shader/QML/Quick");
    qmlAndQuick();
    auto *label = new QLabel(QStringLiteral("SDK_DEPS_OK"));
    label->show();
    EM_ASM({
        document.title = 'SDK_DEPS_OK';
        document.getElementById('status').textContent = 'SDK_DEPS_OK';
        if (new URLSearchParams(location.search).has('test')) fetch('/__probe_result?status=SDK_DEPS_OK');
    });
#ifdef QT_HAVE_EMSCRIPTEN_ASYNCIFY
    return app->exec();
#else
    (void)app;
    return 0;
#endif
}
