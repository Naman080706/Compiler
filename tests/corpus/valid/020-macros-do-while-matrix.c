#include <stdio.h>
#include <math.h>
#define ROWS 2
#define COLS 3
#define SCALE 2.5

int main(void) {
    int grid[ROWS][COLS] = {{1, 2, 3}, {4, 5, 6}};
    const int limit = 3;
    int r, c;
    int count = 0;
    double root;
    for (r = 0, c = 0; r < ROWS; r++) {
        for (c = 0; c < COLS; c++) {
            grid[r][c] *= 2;
        }
    }
    do {
        count++;
    } while (count < limit);
    root = sqrt(grid[1][2] * SCALE) + pow(2, 3);
    printf("%d %d %f\n", grid[0][1], count, root);
    return 0;
}
