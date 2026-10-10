#include <stdio.h>

int main(void) {
    int total = 0;
    int i;
    for (i = 1; i <= 10; i++) {
        total += i;
    }
    printf(total);
    return 0;
}
