#include <stdio.h>

int main(void) {
    int sum = 0;
    int count = 0;
    int i;
    for (i = 1; i <= 10; i++) {
        sum = sum + i
        count++;
    }
    printf("sum = %d after %d steps\n", sum, count);
    return 0;
}
