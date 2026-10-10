#include <stdio.h>

int main(void) {
    int data[5];
    int total = 0;
    for (i = 0; i < 5; i++) {
        data[i] = i * 2 + 1;
    }
    for (i = 0; i < 5; i++) {
        total += data[i];
    }
    printf("total = %d\n", total);
    return 0;
}
