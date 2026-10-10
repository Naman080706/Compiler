#include <stdio.h>

int add(int a, int b) {
    return a + b;
}

int main(void) {
    int total = 0;
    int i;
    for (i = 1; i <= 5; i++) {
        total = add(total);
    }
    printf("total = %d\n", total);
    return 0;
}
