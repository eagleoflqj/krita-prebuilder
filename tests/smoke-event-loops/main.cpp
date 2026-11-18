#include <QApplication>
#include <QDialog>
#include <QEventLoop>
#include <QFileDialog>
#include <QFutureWatcher>
#include <QKeyEvent>
#include <QMenu>
#include <QMessageBox>
#include <QPushButton>
#include <QTimer>
#include <QtConcurrent>
#include <array>
#include <cstdio>
#include <emscripten.h>

static int checks = 0;
static void require(bool condition, const char *name) {
    if (!condition) {
        EM_ASM({ fetch('/__probe_result?status=' + encodeURIComponent('FAIL: ' + UTF8ToString($0)));}, name);
        std::abort();
    }
    ++checks;
    std::printf("PASS: %s\n", name);
}

int main(int argc, char **argv) {
    QApplication app(argc, argv);
    QPushButton button(QStringLiteral("Test synchronous Qt dialogs"));
    button.resize(500, 160);
    button.show();
    QObject::connect(&button, &QPushButton::clicked, &app, [&] {
        std::array<unsigned, 4096> stack{};
        stack.fill(0xdecafbad);
        QDialog accepted;
        QTimer::singleShot(30, &accepted, &QDialog::accept);
        require(accepted.exec() == QDialog::Accepted, "dialog returns Accepted");
        QDialog rejected;
        QTimer::singleShot(30, &rejected, &QDialog::reject);
        require(rejected.exec() == QDialog::Rejected, "dialog returns Rejected");
        require(stack.front() == 0xdecafbad && stack.back() == 0xdecafbad,
                "stack locals survive suspension");
        QEventLoop loop;
        QTimer::singleShot(30, &loop, &QEventLoop::quit);
        loop.exec();
        require(true, "secondary event loop resumes");
        QDialog outer;
        QTimer::singleShot(30, &outer, [&] {
            QDialog inner;
            QTimer::singleShot(30, &inner, &QDialog::accept);
            require(inner.exec() == QDialog::Accepted, "inner dialog returns Accepted");
            outer.accept();
        });
        require(outer.exec() == QDialog::Accepted, "nested dialog stack resumes");
        int destroyed = 0;
        try {
            struct Guard {
                int &count;
                ~Guard() { ++count; }
            } guard{destroyed};
            QDialog resumed;
            QTimer::singleShot(30, &resumed, &QDialog::accept);
            if (resumed.exec() == QDialog::Accepted)
                throw 23;
        } catch (int value) {
            require(value == 23 && destroyed == 1,
                    "C++ exception unwinds resumed stack and runs destructors");
        }
        QTimer::singleShot(30, &app, [] {
            auto *message = qobject_cast<QMessageBox *>(QApplication::activeModalWidget());
            if (message)
                message->button(QMessageBox::Yes)->click();
        });
        require(QMessageBox::question(&button, QStringLiteral("Question"),
                                      QStringLiteral("Continue?")) == QMessageBox::Yes,
                "synchronous message box preserves selected button");
        QFileDialog file(&button);
        file.setOption(QFileDialog::DontUseNativeDialog);
        file.setAcceptMode(QFileDialog::AcceptSave);
        file.selectFile(QStringLiteral("/tmp/probe.kra"));
        QTimer::singleShot(30, &file, [&] { QMetaObject::invokeMethod(&file, "accept"); });
        require(file.exec() == QDialog::Accepted &&
                    file.selectedFiles().value(0) == QStringLiteral("/tmp/probe.kra"),
                "synchronous file dialog preserves selected filename");
        QMenu menu(&button);
        auto *action = menu.addAction(QStringLiteral("Choose"));
        QTimer::singleShot(30, &menu, [&] {
            menu.setActiveAction(action);
            QKeyEvent event(QEvent::KeyPress, Qt::Key_Return, Qt::NoModifier);
            QApplication::sendEvent(&menu, &event);
        });
        require(menu.exec(QPoint(20, 20)) == action, "synchronous menu preserves chosen action");
        auto future = QtConcurrent::run([] {
            try {
                throw 17;
            } catch (int result) {
                return result;
            }
        });
        QFutureWatcher<int> watcher;
        QEventLoop workerLoop;
        QObject::connect(&watcher, &QFutureWatcher<int>::finished, &workerLoop, &QEventLoop::quit);
        watcher.setFuture(future);
        workerLoop.exec();
        require(future.result() == 17,
                "pthreads, C++ exceptions and main-thread suspension coexist");
        require(EM_ASM_INT({ return globalThis.loopHeartbeat > 0;}),
                           "browser event loop remains responsive");
        std::printf("LOOP_PROBE_OK: %d checks\n", checks);
        EM_ASM({ fetch('/__probe_result?status=LOOP_PROBE_OK');});
    });
    QTimer::singleShot(50, &button, &QPushButton::click);
    return app.exec();
}
