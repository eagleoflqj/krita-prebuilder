#include <libintl.h>
#include <locale.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv) {
    if (argc > 1)
        setenv("LC_ALL", argv[1], 1);
    else
        unsetenv("LC_ALL");
    setenv("LANGUAGE", "zh_CN", 1);
    setenv("LANG", "zh_CN.UTF-8", 1);
    setlocale(LC_ALL, "");
    bindtextdomain("sdk-i18n", "/probe/share/locale");
    bind_textdomain_codeset("sdk-i18n", "UTF-8");
    const char *translated = dgettext("sdk-i18n", "Probe");
    const char *expected = argc > 1 ? "Probe" : "探针";
    printf("LC_ALL=%s: %s\n", argc > 1 ? argv[1] : "unset", translated);
    return strcmp(translated, expected) != 0;
}
