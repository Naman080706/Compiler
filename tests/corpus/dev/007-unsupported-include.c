#include <stdio.h>
#include <time.h>

int main(void) {
    int c;
    for (c = 0; c <= 100; c += 25) {
        double f = c * 9.0 / 5.0 + 32.0;
        printf("%d C = %f F\n", c, f);
    }
    return 0;
}
