#include <stdio.h>

int max(a, int b) {
    if (a > b) {
        return a;
    }
    return b;
}

int main(void) {
    int x = 17;
    int y = 42;
    printf("larger of %d and %d is %d\n", x, y, max(x, y));
    return 0;
}
