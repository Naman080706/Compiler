#include <stdio.h>

int main(void) {
    unsigned int flags = 0;
    unsigned int mask = 1u << 3;
    long big = 100000L * 3;
    int a = 12;
    int b = 10;
    int larger = (a > b) ? a : b;
    flags |= mask;
    flags ^= 1;
    flags &= ~2u;
    flags <<= 1;
    printf("%u %d %ld %d\n", flags, larger, big, (int)sizeof(int));
    printf("%d %d\n", a & b, (a | b) >> 1);
    return 0;
}
