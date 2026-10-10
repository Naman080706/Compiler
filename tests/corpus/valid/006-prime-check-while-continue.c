#include <stdio.h>

int is_prime(int n) {
    int d = 2;
    if (n < 2) {
        return 0;
    }
    while (d * d <= n) {
        if (n % d == 0) {
            return 0;
        }
        d++;
    }
    return 1;
}

int main(void) {
    int n = 0;
    int count = 0;
    while (n < 30) {
        n++;
        if (!is_prime(n)) {
            continue;
        }
        printf("%d ", n);
        count++;
    }
    printf("\n%d primes found\n", count);
    return 0;
}
