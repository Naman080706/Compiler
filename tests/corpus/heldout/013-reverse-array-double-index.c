#include <stdio.h>

int main(void) {
    int data[6];
    int i;
    int tmp;
    double half = 3.0;
    for (i = 0; i < 6; i++) {
        data[i] = (i + 1) * 11;
    }
    for (i = 0; i < 3; i++) {
        tmp = data[i];
        data[i] = data[5 - i];
        data[5 - i] = tmp;
    }
    for (i = 0; i < 6; i++) {
        printf("%d ", data[i]);
    }
    printf("\nmiddle element: %d\n", data[half]);
    return 0;
}
