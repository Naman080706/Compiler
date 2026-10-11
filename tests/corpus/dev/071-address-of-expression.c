#include <stdio.h>

int main(void) {
    int a = 2;
    int b = 3;
    int *where = &(a + b);
    printf("%d\n", *where);
    return 0;
}
