#include <stdio.h>

void swap(int *a, int *b) {
    int tmp = *a;
    *a = *b;
    *b = tmp;
}

int sum(const int *values, int n) {
    int total = 0;
    int i;
    for (i = 0; i < n; i++) {
        total += values[i];
    }
    return total;
}

int main(void) {
    int x = 3;
    int y = 8;
    int data[4] = {1, 2, 3, 4};
    int *p = &data[1];
    swap(&x, &y);
    *p += 10;
    p++;
    printf("x=%d y=%d sum=%d next=%d\n", x, y, sum(data, 4), *p);
    return 0;
}
