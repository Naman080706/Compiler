#include <stdio.h>

int main(void) {
    double price = 9.5;
    int *p = &price;
    printf("%p\n", (void *)p);
    return 0;
}
