#include <stdio.h>

int main(void) {
    int sum = 0;
    int temp = 0;
    int i;
    for (i = 1; i <= 10; i++) {
        sum += i;
    }
    printf("sum = %d\n", sum);
    return 0;
}
