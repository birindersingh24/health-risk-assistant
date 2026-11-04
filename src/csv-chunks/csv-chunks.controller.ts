import { Controller, Get, Post, Query } from '@nestjs/common';
import { CsvChunkService } from './csv-chunks.service.js';
import { GuidelineDBService } from '../VectorService/guidelines-db.js';
import { VisitDBService } from '../VectorService/visit-db.js';

@Controller('csv-chunks')
export class CsvChunkController {
  constructor(
    private readonly csvChunkService: CsvChunkService,
    private readonly guidelineDBService: GuidelineDBService,
    private readonly visitDBService: VisitDBService,
  ) {}

  @Post('guidelines-chunk')
  async guidelinesChunkingAndEmbedding() {
    try {
      const chunks = await this.csvChunkService.createGuidelinesChunk();
      const vectors = await this.csvChunkService.embeddingChunks(chunks);
      await this.guidelineDBService.upsertGuidelines(
        chunks.map((c, i) => ({ ...c, embedding: vectors[i] })),
      );
      return { message: 'Embeddings stored in DB', upserted: chunks.length };
    } catch (err) {
      console.error('Error in guidelinesChunkingAndEmbedding:', err);
      throw err;
    }
  }

  @Post('patient-chunk')
  async chunkingAndEmbedding() {
    const chunks = await this.csvChunkService.createPatientChunk();
    const vectors = await this.csvChunkService.embeddingChunks(chunks);
    await this.visitDBService.upsertPatients(
      chunks.map((c, i) => ({ ...c, embedding: vectors[i] })),
    );
    return { upserted: chunks.length };
  }

  @Get('search-guidelines')
  async search(
    @Query('q') q: string,
    @Query('diseaseTitle') diseaseTitle?: string,
  ) {
    try {
      const [vector] = await this.csvChunkService.embeddingChunks([
        { text: q },
      ]);
      return this.guidelineDBService.search(vector, 5, diseaseTitle);
    } catch (err) {
      console.error('Error in search:', err);
      throw err;
    }
  }

  @Get('search-llm')
  async searchLLM(
    @Query('q') q: string
  ) {
    try {
      const [vector] = await this.csvChunkService.embeddingChunks([
        { text: q },
      ]);
      return this.csvChunkService.searchLLM(vector, q);
    } catch (err) {
      console.error('Error in search:', err);
      throw err;
    }
  }
}
