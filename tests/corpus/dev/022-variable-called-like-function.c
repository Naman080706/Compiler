#include <stdio.h>

int max(int x, int y) {
    if (x > y) {
        return x;
    }
    return y;
}

int main(void) {
    int a = 12;
    int b = 30;
    int max = 0;
    max = max(a, b);
    printf("larger = %d\n", max);
    return 0;
}
