#include <stdio.h>
#include <string.h>
#include <ctype.h>

int main(void) {
    char name[20] = "compiler";
    char copy[20];
    char *p;
    size_t len;
    strcpy(copy, name);
    len = strlen(copy);
    for (p = copy; *p != '\0'; p++) {
        *p = toupper(*p);
    }
    if (strcmp(name, copy) != 0) {
        printf("%s -> %s (%d letters)\n", name, copy, (int)len);
    }
    return 0;
}
