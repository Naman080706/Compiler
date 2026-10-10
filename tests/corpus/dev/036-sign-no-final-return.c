#include <stdio.h>

int sign(int n) {
    if (n > 0) {
        return 1;
    } else if (n < 0) {
        return -1;
    }
}

int main(void) {
    int a = -8;
    int b = 5;
    printf("sign of %d is %d\n", a, sign(a));
    printf("sign of %d is %d\n", b, sign(b));
    return 0;
}
