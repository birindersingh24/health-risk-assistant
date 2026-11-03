import { Controller, Get, Post, Query } from '@nestjs/common';
import { CsvChunkService } from './csv-chunks.service.js';
import { PineconeService } from '../vectorService.js';

@Controller('csv-chunks')
export class CsvChunkController {
  constructor(
    private readonly csvChunkService: CsvChunkService,
    private readonly pineconeService: PineconeService,
  ) {}

  @Post('insert')
  async chunkingAndEmbedding() {
    const chunks = await this.csvChunkService.createChunks();
    const vectors = await this.csvChunkService.embeddingChunks(chunks);
    await this.pineconeService.upsertVisits(
      chunks.map((c, i) => ({ ...c, embedding: vectors[i] })),
    );
    return { upserted: chunks.length };
  }

  @Get('search')
  async search(@Query('q') q: string, @Query('patientId') patientId?: string) {
    const [vector] = await this.csvChunkService.embeddingChunks([{ text: q }]);
    return this.pineconeService.search(vector, 5, patientId);
  }
}
