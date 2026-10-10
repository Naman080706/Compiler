#include <stdio.h>

int larger(int a, int b) {
    int result = b;
    if (a > b) {
        result = a;
    return result;
}

int main(void) {
    int x = 17;
    int y = 42;
    printf("larger of %d and %d is %d\n", x, y, larger(x, y));
    printf("larger of 5 and 3 is %d\n", larger(5, 3));
    return 0;
}
